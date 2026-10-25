"""Model Context Protocol (MCP) server implementation for Google Assistant Entity Console.

Adheres to MCP specification revision 2026-07-28 (Streamable HTTP Transport).
Provides stateless JSON-RPC 2.0 dispatching for inspecting and configuring entities,
voice aliases, blocklists, and Google HomeGraph synchronization.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

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

    # Notifications without id do not receive error responses
    if is_notification:
        return None

    return _jsonrpc_error(-32601, f"Method not found: {method}", req_id)
