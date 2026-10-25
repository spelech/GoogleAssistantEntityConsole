"""Model Context Protocol (MCP) server implementation for Google Assistant Entity Console.

Adheres to MCP specification revision 2026-07-28 (Streamable HTTP Transport).
Provides stateless JSON-RPC 2.0 dispatching for inspecting and configuring entities,
voice aliases, blocklists, and Google HomeGraph synchronization.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry,
    device_registry,
    entity_registry,
    floor_registry,
)

from .const import DOMAIN
from .store import async_get_store
from .views import async_fetch_entities_data, async_load_blocklist

_LOGGER = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2026-07-28"
SERVER_NAME = "google-assistant-entity-console"
SERVER_VERSION = "3.0.2"
TOOL_CACHE_TTL_MS = 300000

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_entities",
        "description": "Queries entities registered in Home Assistant along with their Google Assistant status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Filter by domain (e.g. light, switch, climate).",
                },
                "area": {
                    "type": "string",
                    "description": "Filter by area/room name or area ID.",
                },
                "floor": {
                    "type": "string",
                    "description": "Filter by floor name or floor ID.",
                },
                "exposure_status": {
                    "type": "string",
                    "enum": ["all", "exposed", "not_exposed", "blocked"],
                    "default": "all",
                    "description": "Filter by exposure status.",
                },
                "search": {
                    "type": "string",
                    "description": "Text search across entity IDs, friendly names, and voice aliases.",
                },
            },
        },
    },
    {
        "name": "get_entity",
        "description": "Retrieves detailed Google Assistant configuration for a single entity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Target entity ID.",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "get_google_assistant_status",
        "description": "Checks cloud project status, credentials state, and exposure counts.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "set_entity_exposure",
        "description": "Exposes or unexposes one or more entities to Google Assistant in .storage and memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entity ID(s) to modify.",
                },
                "exposed": {
                    "type": "boolean",
                    "description": "true to expose, false to exclude.",
                },
            },
            "required": ["entity_ids", "exposed"],
        },
    },
    {
        "name": "set_entity_nicknames",
        "description": "Modifies voice aliases used by Google Assistant for voice matching.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Target entity ID.",
                },
                "nicknames": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of voice nickname strings.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "append", "remove"],
                    "default": "replace",
                    "description": "Mutation mode: replace, append, or remove.",
                },
            },
            "required": ["entity_id", "nicknames"],
        },
    },
    {
        "name": "manage_blocklist_rule",
        "description": "Adds or removes a regular expression blocklist filter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove"],
                    "description": "Action to perform: add or remove.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern string (e.g. .*_battery_level$).",
                },
            },
            "required": ["action", "pattern"],
        },
    },
    {
        "name": "sync_to_google",
        "description": "Triggers real-time zero-reboot devices:requestSync to Google HomeGraph.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _jsonrpc_error(code: int, message: str, req_id: Any = None, data: Any = None) -> dict[str, Any]:
    """Format a JSON-RPC 2.0 error response."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": error,
    }


def _jsonrpc_result(result: Any, req_id: Any) -> dict[str, Any]:
    """Format a JSON-RPC 2.0 success response."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
    }


def _format_entity_response(entity_data: dict[str, Any]) -> dict[str, Any]:
    """Format entity dictionary into standard MCP tool output."""
    entity_id = entity_data["entity_id"]
    display_name = (
        entity_data.get("display_name")
        or entity_data.get("friendly_name")
        or entity_data.get("name")
        or entity_id
    )
    aliases = list(entity_data.get("aliases") or entity_data.get("nicknames") or [])
    is_exposed = bool(
        entity_data.get("should_expose")
        or entity_data.get("yaml_exposed")
        or entity_data.get("exposed")
    )

    return {
        "entity_id": entity_id,
        "name": entity_data.get("name"),
        "original_name": entity_data.get("original_name"),
        "display_name": display_name,
        "friendly_name": display_name,
        "device_class": entity_data.get("device_class") or "",
        "platform": entity_data.get("platform") or "",
        "should_expose": bool(entity_data.get("should_expose", False)),
        "yaml_exposed": bool(entity_data.get("yaml_exposed", False)),
        "exposed": is_exposed,
        "area": entity_data.get("area") or "TBA",
        "floor": entity_data.get("floor") or "TBA",
        "domain": entity_data.get("domain") or entity_id.split(".")[0],
        "aliases": aliases,
        "nicknames": aliases,
        "in_group": bool(entity_data.get("in_group", False)),
        "unavailable": bool(entity_data.get("unavailable", False)),
        "blocklisted": bool(entity_data.get("blocklisted", False)),
        "blocklist_rule": entity_data.get("blocklist_rule"),
    }


def _get_blocked_entities(
    hass: HomeAssistant, compiled_blocklist: list[tuple[str, re.Pattern]]
) -> list[dict[str, Any]]:
    """Find entities in registry that are blocked by current blocklist rules."""
    if not compiled_blocklist:
        return []

    ent_reg = entity_registry.async_get(hass)
    dev_reg = device_registry.async_get(hass)
    area_reg = area_registry.async_get(hass)
    floor_reg = floor_registry.async_get(hass)

    raw_entities = getattr(ent_reg, "entities", {})
    if not isinstance(raw_entities, dict):
        return []

    area_map = {
        a.id: a.name
        for a in getattr(area_reg, "async_list_areas", lambda: [])()
    }
    area_floor_map = {
        a.id: getattr(a, "floor_id", None)
        for a in getattr(area_reg, "async_list_areas", lambda: [])()
    }
    floor_map = {
        getattr(f, "floor_id", getattr(f, "id", None)): f.name
        for f in getattr(floor_reg, "async_list_floors", lambda: [])()
        if getattr(f, "floor_id", getattr(f, "id", None))
    }

    devices_dict = getattr(dev_reg, "devices", {})
    device_vals = devices_dict.values() if isinstance(devices_dict, dict) else []
    device_area_map = {d.id: d.area_id for d in device_vals if hasattr(d, "id")}
    device_name_map = {
        d.id: getattr(d, "name_by_user", None) or getattr(d, "name", "")
        for d in device_vals
        if hasattr(d, "id")
    }

    blocked: list[dict[str, Any]] = []
    for entry in raw_entities.values():
        if getattr(entry, "disabled_by", None) or getattr(entry, "hidden_by", None):
            continue
        entity_id = getattr(entry, "entity_id", "")
        matched_rule = None
        for pattern_str, rx in compiled_blocklist:
            if rx.search(entity_id):
                matched_rule = pattern_str
                break
        if not matched_rule:
            continue

        device_id = getattr(entry, "device_id", None)
        domain = entity_id.split(".")[0]
        area_id = getattr(entry, "area_id", None) or device_area_map.get(device_id)
        area_name = area_map.get(area_id, "TBA") if area_id else "TBA"
        floor_id = area_floor_map.get(area_id) if area_id else None
        floor_name = floor_map.get(floor_id, "TBA") if floor_id else "TBA"

        name = getattr(entry, "name", None)
        if not isinstance(name, str):
            name = None
        orig_name = getattr(entry, "original_name", None)
        if not isinstance(orig_name, str):
            orig_name = None

        display_name = name
        if not display_name and device_id and isinstance(device_id, str):
            display_name = device_name_map.get(device_id)
        if not display_name:
            display_name = orig_name
        if not display_name:
            display_name = entity_id.split(".")[-1].replace("_", " ").title()

        device_class = getattr(entry, "device_class", None) or getattr(entry, "original_device_class", None) or ""
        if not isinstance(device_class, str):
            device_class = ""

        platform = getattr(entry, "platform", None) or ""
        if not isinstance(platform, str):
            platform = ""

        raw_aliases = getattr(entry, "aliases", []) or []
        clean_aliases = [str(a) for a in raw_aliases if isinstance(a, (str, int, float)) and str(a) != "0" and a]

        blocked.append({
            "entity_id": entity_id,
            "name": name,
            "original_name": orig_name,
            "display_name": str(display_name),
            "friendly_name": str(display_name),
            "device_class": device_class,
            "platform": platform,
            "should_expose": False,
            "yaml_exposed": False,
            "exposed": False,
            "area": area_name,
            "floor": floor_name,
            "domain": domain,
            "aliases": clean_aliases,
            "nicknames": clean_aliases,
            "in_group": False,
            "unavailable": False,
            "blocklisted": True,
            "blocklist_rule": matched_rule,
        })
    return blocked


async def _handle_list_entities(hass: HomeAssistant, args: dict[str, Any]) -> dict[str, Any]:
    """Execute list_entities tool with filtering."""
    exposure_status = args.get("exposure_status", "all")
    domain_filter = args.get("domain")
    area_filter = args.get("area")
    floor_filter = args.get("floor")
    search_filter = args.get("search")

    raw_blocklist = await async_load_blocklist(hass)
    compiled_blocklist: list[tuple[str, re.Pattern]] = []
    for pattern in raw_blocklist:
        with contextlib.suppress(re.error):
            compiled_blocklist.append((pattern, re.compile(pattern)))

    if exposure_status == "blocked":
        candidates = _get_blocked_entities(hass, compiled_blocklist)
    else:
        active = await async_fetch_entities_data(hass)
        formatted_active = [_format_entity_response(e) for e in active]
        if exposure_status == "exposed":
            candidates = [e for e in formatted_active if e["exposed"]]
        elif exposure_status == "not_exposed":
            candidates = [e for e in formatted_active if not e["exposed"]]
        else:
            candidates = formatted_active

    # Resolve area filter mappings
    matched_area_names: set[str] = set()
    if area_filter:
        area_filter_lower = area_filter.lower().strip()
        matched_area_names.add(area_filter_lower)
        area_reg = area_registry.async_get(hass)
        if hasattr(area_reg, "async_list_areas"):
            for a in area_reg.async_list_areas():
                if a.id.lower() == area_filter_lower or a.name.lower() == area_filter_lower:
                    matched_area_names.add(a.name.lower())

    # Resolve floor filter mappings
    matched_floor_names: set[str] = set()
    if floor_filter:
        floor_filter_lower = floor_filter.lower().strip()
        matched_floor_names.add(floor_filter_lower)
        floor_reg = floor_registry.async_get(hass)
        if hasattr(floor_reg, "async_list_floors"):
            for f in floor_reg.async_list_floors():
                fid = getattr(f, "floor_id", getattr(f, "id", None))
                if (fid and fid.lower() == floor_filter_lower) or (f.name and f.name.lower() == floor_filter_lower):
                    matched_floor_names.add(f.name.lower())

    results: list[dict[str, Any]] = []
    for ent in candidates:
        if domain_filter and ent.get("domain", "").lower() != domain_filter.lower().strip():
            continue

        if area_filter and ent.get("area", "").lower() not in matched_area_names:
            continue

        if floor_filter and ent.get("floor", "").lower() not in matched_floor_names:
            continue

        if search_filter:
            term = search_filter.lower().strip()
            eid = ent.get("entity_id", "").lower()
            fname = (
                ent.get("friendly_name")
                or ent.get("display_name")
                or ent.get("name")
                or ""
            ).lower()
            aliases = [str(a).lower() for a in ent.get("nicknames", [])]
            if term not in eid and term not in fname and not any(term in a for a in aliases):
                continue

        results.append(ent)

    return {
        "content": [{"type": "text", "text": json.dumps(results, indent=2)}],
    }


async def _handle_get_entity(hass: HomeAssistant, args: dict[str, Any]) -> dict[str, Any]:
    """Execute get_entity tool."""
    entity_id = args.get("entity_id")
    if not entity_id or not isinstance(entity_id, str):
        return {
            "content": [{"type": "text", "text": "Missing required argument: entity_id"}],
            "isError": True,
        }

    entities = await async_fetch_entities_data(hass)
    match = next((e for e in entities if e.get("entity_id") == entity_id), None)
    if match:
        formatted = _format_entity_response(match)
        return {
            "content": [{"type": "text", "text": json.dumps(formatted, indent=2)}],
        }

    # Check if entity is in blocklist
    raw_blocklist = await async_load_blocklist(hass)
    compiled_blocklist: list[tuple[str, re.Pattern]] = []
    for pattern in raw_blocklist:
        with contextlib.suppress(re.error):
            compiled_blocklist.append((pattern, re.compile(pattern)))

    blocked_entities = _get_blocked_entities(hass, compiled_blocklist)
    blocked_match = next((e for e in blocked_entities if e.get("entity_id") == entity_id), None)
    if blocked_match:
        return {
            "content": [{"type": "text", "text": json.dumps(blocked_match, indent=2)}],
        }

    return {
        "content": [{"type": "text", "text": f"Entity '{entity_id}' not found"}],
        "isError": True,
    }


async def _handle_get_google_assistant_status(
    hass: HomeAssistant, args: dict[str, Any]
) -> dict[str, Any]:
    """Execute get_google_assistant_status tool."""
    store = await async_get_store(hass)
    gs = store.google_settings
    project_id = gs.get("project_id", "")
    sa = gs.get("service_account")
    sa_configured = bool(
        isinstance(sa, dict)
        and sa.get("client_email")
        and sa.get("private_key")
    )
    report_state = bool(gs.get("report_state", True))

    entities = await async_fetch_entities_data(hass)
    exposed_count = sum(
        1 for e in entities if e.get("should_expose") or e.get("yaml_exposed")
    )
    if not entities and store.synced_entities:
        exposed_count = len(store.synced_entities)

    raw_blocklist = await async_load_blocklist(hass)
    compiled_blocklist: list[re.Pattern] = []
    for pattern in raw_blocklist:
        with contextlib.suppress(re.error):
            compiled_blocklist.append(re.compile(pattern))

    ent_reg = entity_registry.async_get(hass)
    raw_entities = getattr(ent_reg, "entities", {})
    ent_values = list(raw_entities.values()) if isinstance(raw_entities, dict) else []
    blocklisted_count = 0
    if compiled_blocklist:
        for entry in ent_values:
            eid = getattr(entry, "entity_id", "")
            if any(rx.search(eid) for rx in compiled_blocklist):
                blocklisted_count += 1

    domain_data = (
        hass.data.get(DOMAIN, {})
        if isinstance(getattr(hass, "data", None), dict)
        else {}
    )
    last_sync = domain_data.get("last_sync_timestamp") or gs.get("last_sync_timestamp")

    status = {
        "project_id": project_id,
        "service_account_configured": sa_configured,
        "report_state": report_state,
        "exposed_count": exposed_count,
        "blocklisted_count": blocklisted_count,
        "last_sync_timestamp": last_sync,
    }

    return {
        "content": [{"type": "text", "text": json.dumps(status, indent=2)}],
    }



async def async_handle_mcp_payload(hass: HomeAssistant, payload: Any) -> dict[str, Any] | None:
    """Route and handle an incoming MCP JSON-RPC payload.

    Args:
        hass: Home Assistant core instance.
        payload: Decoded JSON payload.

    Returns:
        JSON-RPC 2.0 response dictionary, or None for notifications.
    """
    if not isinstance(payload, dict):
        return _jsonrpc_error(-32600, "Invalid Request: payload must be a JSON object", None)

    req_id = payload.get("id")
    is_notification = "id" not in payload

    if payload.get("jsonrpc") != "2.0":
        return _jsonrpc_error(-32600, "Invalid Request: missing or invalid jsonrpc 2.0 version", req_id)

    method = payload.get("method")
    if not isinstance(method, str):
        return _jsonrpc_error(-32600, "Invalid Request: method must be a string", req_id)

    params = payload.get("params")
    if params is not None and not isinstance(params, (dict, list)):
        return _jsonrpc_error(-32602, "Invalid params: expected object or array", req_id)

    # Lifecycle & core handlers
    if method == "ping":
        return _jsonrpc_result({}, req_id)

    if method == "initialize":
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
        }
        return _jsonrpc_result(result, req_id)

    if method == "notifications/initialized":
        # Client notification confirming initialization receipt
        return None

    if method == "tools/list":
        result = {
            "tools": TOOL_DEFINITIONS,
            "ttlMs": TOOL_CACHE_TTL_MS,
        }
        return _jsonrpc_result(result, req_id)

    if method == "tools/call":
        if not isinstance(params, dict):
            return _jsonrpc_error(-32602, "Invalid params: expected object", req_id)
        name = params.get("name")
        if not name or not isinstance(name, str):
            return _jsonrpc_error(-32602, "Missing or invalid tool name", req_id)
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _jsonrpc_error(-32602, "Invalid arguments: expected object", req_id)

        if name == "list_entities":
            res = await _handle_list_entities(hass, arguments)
            return _jsonrpc_result(res, req_id)
        if name == "get_entity":
            res = await _handle_get_entity(hass, arguments)
            return _jsonrpc_result(res, req_id)
        if name == "get_google_assistant_status":
            res = await _handle_get_google_assistant_status(hass, arguments)
            return _jsonrpc_result(res, req_id)

        return _jsonrpc_result(
            {
                "content": [
                    {
                        "type": "text",
                        "text": f"Tool '{name}' is not implemented or unknown",
                    }
                ],
                "isError": True,
            },
            req_id,
        )

    # Notifications without id do not receive error responses
    if is_notification:
        return None

    return _jsonrpc_error(-32601, f"Method not found: {method}", req_id)
