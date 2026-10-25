"""Tests for MCP server protocol dispatcher, schemas, and lifecycle."""

from __future__ import annotations

import pytest

from custom_components.google_assistant_entity_console.mcp import (
    MCP_PROTOCOL_VERSION,
    TOOL_DEFINITIONS,
    async_handle_mcp_payload,
)
from custom_components.google_assistant_entity_console.views import McpStreamableView


@pytest.mark.asyncio
async def test_mcp_protocol_version():
    """Test protocol version constant matches 2026-07-28."""
    assert MCP_PROTOCOL_VERSION == "2026-07-28"


def test_tool_definitions_structure():
    """Test TOOL_DEFINITIONS structure and tool count."""
    assert len(TOOL_DEFINITIONS) == 7
    for tool in TOOL_DEFINITIONS:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


@pytest.mark.asyncio
async def test_mcp_ping(mock_hass):
    """Test ping method returns empty result."""
    req = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res == {"jsonrpc": "2.0", "id": 1, "result": {}}


@pytest.mark.asyncio
async def test_mcp_initialize(mock_hass):
    """Test initialize method returns server capabilities and protocol version."""
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "initialize",
        "params": {
            "protocolVersion": "2026-07-28",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == 2
    assert res["result"]["protocolVersion"] == "2026-07-28"
    assert res["result"]["serverInfo"]["name"] == "google-assistant-entity-console"


@pytest.mark.asyncio
async def test_mcp_notifications_initialized(mock_hass):
    """Test notifications/initialized notification payload (no id)."""
    req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    res = await async_handle_mcp_payload(mock_hass, req)
    # Notifications without id do not require a JSON-RPC response
    assert res is None or res == {}


@pytest.mark.asyncio
async def test_mcp_tools_list(mock_hass):
    """Test tools/list returns all 7 tools and 5-minute cache hint."""
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == 3
    tools = res["result"]["tools"]
    assert len(tools) == 7
    tool_names = [t["name"] for t in tools]
    assert "list_entities" in tool_names
    assert "get_entity" in tool_names
    assert "get_google_assistant_status" in tool_names
    assert "set_entity_exposure" in tool_names
    assert "set_entity_nicknames" in tool_names
    assert "manage_blocklist_rule" in tool_names
    assert "sync_to_google" in tool_names
    assert res["result"]["ttlMs"] == 300000


@pytest.mark.asyncio
async def test_mcp_invalid_jsonrpc(mock_hass):
    """Test invalid JSON-RPC payload returns code -32600."""
    req = {"id": 4, "method": "unknown_method"}
    res = await async_handle_mcp_payload(mock_hass, req)
    assert "error" in res
    assert res["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_mcp_non_dict_payload(mock_hass):
    """Test non-dict payload returns code -32600."""
    res = await async_handle_mcp_payload(mock_hass, "not-a-dict")
    assert "error" in res
    assert res["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_mcp_invalid_params(mock_hass):
    """Test invalid params type returns code -32602."""
    req = {"jsonrpc": "2.0", "id": 6, "method": "initialize", "params": "string_not_dict"}
    res = await async_handle_mcp_payload(mock_hass, req)
    assert "error" in res
    assert res["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_mcp_method_not_found(mock_hass):
    """Test unknown method returns code -32601."""
    req = {"jsonrpc": "2.0", "id": 5, "method": "non_existent_method"}
    res = await async_handle_mcp_payload(mock_hass, req)
    assert "error" in res
    assert res["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_mcp_call_list_entities(mock_hass):
    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "list_entities",
            "arguments": {"domain": "light", "exposure_status": "all"},
        },
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == 10
    assert not res["result"].get("isError", False)
    content = res["result"]["content"]
    assert len(content) > 0
    assert content[0]["type"] == "text"


@pytest.mark.asyncio
async def test_mcp_call_get_entity(mock_hass):
    req = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "get_entity",
            "arguments": {"entity_id": "light.living_room_lights"},
        },
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == 11


@pytest.mark.asyncio
async def test_mcp_call_get_google_assistant_status(mock_hass):
    req = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {"name": "get_google_assistant_status", "arguments": {}},
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert not res["result"].get("isError", False)


@pytest.mark.asyncio
async def test_mcp_call_list_entities_filtering(mock_hass):
    """Test filtering by domain, area, floor, exposure status, and search."""
    import json
    from unittest.mock import patch

    sample_entities = [
        {
            "entity_id": "light.living_room_ceiling",
            "name": "Ceiling Light",
            "original_name": "Hue Lamp",
            "display_name": "Living Room Ceiling Light",
            "device_class": "",
            "platform": "hue",
            "should_expose": True,
            "yaml_exposed": True,
            "area": "Living Room",
            "floor": "First Floor",
            "domain": "light",
            "aliases": ["overhead light", "main light"],
            "in_group": False,
            "unavailable": False,
        },
        {
            "entity_id": "switch.kitchen_fan",
            "name": "Exhaust Fan",
            "original_name": "Fan",
            "display_name": "Kitchen Fan",
            "device_class": "fan",
            "platform": "esphome",
            "should_expose": False,
            "yaml_exposed": False,
            "area": "Kitchen",
            "floor": "First Floor",
            "domain": "switch",
            "aliases": ["cooker fan"],
            "in_group": False,
            "unavailable": False,
        },
        {
            "entity_id": "climate.upstairs_thermostat",
            "name": "Upstairs Thermostat",
            "original_name": "Ecobee",
            "display_name": "Upstairs Thermostat",
            "device_class": "",
            "platform": "ecobee",
            "should_expose": True,
            "yaml_exposed": False,
            "area": "Master Bedroom",
            "floor": "Second Floor",
            "domain": "climate",
            "aliases": ["bedroom ac"],
            "in_group": False,
            "unavailable": False,
        },
    ]

    with patch(
        "custom_components.google_assistant_entity_console.mcp.async_fetch_entities_data",
        return_value=sample_entities,
    ):
        # 1. Filter domain = 'switch'
        req1 = {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {"name": "list_entities", "arguments": {"domain": "switch"}},
        }
        res1 = await async_handle_mcp_payload(mock_hass, req1)
        data1 = json.loads(res1["result"]["content"][0]["text"])
        assert len(data1) == 1
        assert data1[0]["entity_id"] == "switch.kitchen_fan"

        # 2. Filter area = 'Living Room'
        req2 = {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {"name": "list_entities", "arguments": {"area": "Living Room"}},
        }
        res2 = await async_handle_mcp_payload(mock_hass, req2)
        data2 = json.loads(res2["result"]["content"][0]["text"])
        assert len(data2) == 1
        assert data2[0]["entity_id"] == "light.living_room_ceiling"

        # 3. Filter floor = 'Second Floor'
        req3 = {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {"name": "list_entities", "arguments": {"floor": "Second Floor"}},
        }
        res3 = await async_handle_mcp_payload(mock_hass, req3)
        data3 = json.loads(res3["result"]["content"][0]["text"])
        assert len(data3) == 1
        assert data3[0]["entity_id"] == "climate.upstairs_thermostat"

        # 4. Filter exposure_status = 'exposed'
        req4 = {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "tools/call",
            "params": {"name": "list_entities", "arguments": {"exposure_status": "exposed"}},
        }
        res4 = await async_handle_mcp_payload(mock_hass, req4)
        data4 = json.loads(res4["result"]["content"][0]["text"])
        assert len(data4) == 2
        assert {d["entity_id"] for d in data4} == {
            "light.living_room_ceiling",
            "climate.upstairs_thermostat",
        }

        # 5. Filter exposure_status = 'not_exposed'
        req5 = {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "tools/call",
            "params": {"name": "list_entities", "arguments": {"exposure_status": "not_exposed"}},
        }
        res5 = await async_handle_mcp_payload(mock_hass, req5)
        data5 = json.loads(res5["result"]["content"][0]["text"])
        assert len(data5) == 1
        assert data5[0]["entity_id"] == "switch.kitchen_fan"

        # 6. Filter search by alias
        req6 = {
            "jsonrpc": "2.0",
            "id": 25,
            "method": "tools/call",
            "params": {"name": "list_entities", "arguments": {"search": "bedroom ac"}},
        }
        res6 = await async_handle_mcp_payload(mock_hass, req6)
        data6 = json.loads(res6["result"]["content"][0]["text"])
        assert len(data6) == 1
        assert data6[0]["entity_id"] == "climate.upstairs_thermostat"


@pytest.mark.asyncio
async def test_mcp_call_get_entity_found_and_not_found(mock_hass):
    """Test get_entity tool when entity is present vs missing."""
    import json
    from unittest.mock import patch

    sample_entities = [
        {
            "entity_id": "light.living_room_lights",
            "name": "Living Room Lights",
            "original_name": "Hue Group",
            "display_name": "Living Room Lights",
            "device_class": "",
            "platform": "hue",
            "should_expose": True,
            "yaml_exposed": True,
            "area": "Living Room",
            "floor": "Ground Floor",
            "domain": "light",
            "aliases": ["overhead"],
            "in_group": True,
            "unavailable": False,
        }
    ]

    with patch(
        "custom_components.google_assistant_entity_console.mcp.async_fetch_entities_data",
        return_value=sample_entities,
    ):
        # Found
        req_found = {
            "jsonrpc": "2.0",
            "id": 30,
            "method": "tools/call",
            "params": {
                "name": "get_entity",
                "arguments": {"entity_id": "light.living_room_lights"},
            },
        }
        res_found = await async_handle_mcp_payload(mock_hass, req_found)
        assert res_found["jsonrpc"] == "2.0"
        assert res_found["id"] == 30
        assert not res_found["result"].get("isError", False)
        ent = json.loads(res_found["result"]["content"][0]["text"])
        assert ent["entity_id"] == "light.living_room_lights"

        # Not found
        req_not_found = {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "tools/call",
            "params": {
                "name": "get_entity",
                "arguments": {"entity_id": "light.non_existent"},
            },
        }
        res_not_found = await async_handle_mcp_payload(mock_hass, req_not_found)
        assert res_not_found["jsonrpc"] == "2.0"
        assert res_not_found["id"] == 31
        assert res_not_found["result"].get("isError") is True
        assert "not found" in res_not_found["result"]["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_mcp_call_get_google_assistant_status_fields(mock_hass):
    """Test get_google_assistant_status returns expected fields."""
    import json
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_store = MagicMock()
    mock_store.google_settings = {
        "project_id": "my-google-project",
        "service_account": {"client_email": "test@example.com", "private_key": "-----BEGIN KEY-----"},
        "report_state": True,
    }
    mock_store.synced_entities = {"light.one": {}, "light.two": {}}
    mock_store.blocklist = ["^camera\\."]

    with patch(
        "custom_components.google_assistant_entity_console.mcp.async_get_store",
        AsyncMock(return_value=mock_store),
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.async_fetch_entities_data",
        AsyncMock(return_value=[{"entity_id": "light.one", "should_expose": True, "yaml_exposed": True}]),
    ):
        req = {
            "jsonrpc": "2.0",
            "id": 40,
            "method": "tools/call",
            "params": {"name": "get_google_assistant_status", "arguments": {}},
        }
        res = await async_handle_mcp_payload(mock_hass, req)
        assert res["jsonrpc"] == "2.0"
        assert not res["result"].get("isError", False)
        status = json.loads(res["result"]["content"][0]["text"])
        assert status["project_id"] == "my-google-project"
        assert status["service_account_configured"] is True
        assert status["report_state"] is True
        assert status["exposed_count"] == 1
        assert "blocklisted_count" in status
        assert "last_sync_timestamp" in status


@pytest.mark.asyncio
async def test_mcp_call_get_google_assistant_status_blocklist_parity(mock_hass):
    """Test get_google_assistant_status blocklisted_count filters out disabled and hidden entities."""
    import json
    from unittest.mock import AsyncMock, MagicMock, patch

    entry_active = MagicMock()
    entry_active.entity_id = "sensor.active_battery"
    entry_active.disabled_by = None
    entry_active.hidden_by = None

    entry_disabled = MagicMock()
    entry_disabled.entity_id = "sensor.disabled_battery"
    entry_disabled.disabled_by = "user"
    entry_disabled.hidden_by = None

    entry_hidden = MagicMock()
    entry_hidden.entity_id = "sensor.hidden_battery"
    entry_hidden.disabled_by = None
    entry_hidden.hidden_by = "integration"

    mock_ent_reg = MagicMock()
    mock_ent_reg.entities = {
        "sensor.active_battery": entry_active,
        "sensor.disabled_battery": entry_disabled,
        "sensor.hidden_battery": entry_hidden,
    }

    mock_store = MagicMock()
    mock_store.google_settings = {}
    mock_store.synced_entities = {}

    with patch(
        "custom_components.google_assistant_entity_console.mcp.async_get_store",
        AsyncMock(return_value=mock_store),
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.async_fetch_entities_data",
        AsyncMock(return_value=[]),
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.async_load_blocklist",
        return_value=[r".*_battery$"],
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.entity_registry.async_get",
        return_value=mock_ent_reg,
    ):
        req = {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {"name": "get_google_assistant_status", "arguments": {}},
        }
        res = await async_handle_mcp_payload(mock_hass, req)
        assert res["jsonrpc"] == "2.0"
        status = json.loads(res["result"]["content"][0]["text"])
        # Only active_battery should be counted (1), not disabled or hidden (total 3 matching regex)
        assert status["blocklisted_count"] == 1


@pytest.mark.asyncio
async def test_mcp_call_list_entities_blocked_exposure_status(mock_hass):
    """Test list_entities returns blocked entities when exposure_status='blocked'."""
    import json
    from unittest.mock import MagicMock, patch

    mock_entry = MagicMock()
    mock_entry.entity_id = "sensor.blocked_battery"
    mock_entry.name = "Blocked Battery"
    mock_entry.original_name = "Battery"
    mock_entry.disabled_by = None
    mock_entry.hidden_by = None
    mock_entry.device_id = None
    mock_entry.area_id = None
    mock_entry.aliases = []

    mock_ent_reg = MagicMock()
    mock_ent_reg.entities = {"sensor.blocked_battery": mock_entry}

    with patch(
        "custom_components.google_assistant_entity_console.mcp.async_load_blocklist",
        return_value=[r".*_battery$"],
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.entity_registry.async_get",
        return_value=mock_ent_reg,
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.device_registry.async_get",
        return_value=MagicMock(devices={}),
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.area_registry.async_get",
        return_value=MagicMock(async_list_areas=MagicMock(return_value=[])),
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.floor_registry.async_get",
        return_value=MagicMock(async_list_floors=MagicMock(return_value=[])),
    ):
        req = {
            "jsonrpc": "2.0",
            "id": 50,
            "method": "tools/call",
            "params": {"name": "list_entities", "arguments": {"exposure_status": "blocked"}},
        }
        res = await async_handle_mcp_payload(mock_hass, req)
        assert res["jsonrpc"] == "2.0"
        data = json.loads(res["result"]["content"][0]["text"])
        assert len(data) == 1
        assert data[0]["entity_id"] == "sensor.blocked_battery"
        assert data[0]["blocklisted"] is True
        assert data[0]["blocklist_rule"] == r".*_battery$"


@pytest.mark.asyncio
async def test_mcp_call_get_entity_blocked(mock_hass):
    """Test get_entity returns entity details even if blocked by blocklist."""
    import json
    from unittest.mock import MagicMock, patch

    mock_entry = MagicMock()
    mock_entry.entity_id = "sensor.blocked_battery"
    mock_entry.name = "Blocked Battery"
    mock_entry.original_name = "Battery"
    mock_entry.disabled_by = None
    mock_entry.hidden_by = None
    mock_entry.device_id = None
    mock_entry.area_id = None
    mock_entry.aliases = []

    mock_ent_reg = MagicMock()
    mock_ent_reg.entities = {"sensor.blocked_battery": mock_entry}

    with patch(
        "custom_components.google_assistant_entity_console.mcp.async_fetch_entities_data",
        return_value=[],
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.async_load_blocklist",
        return_value=[r".*_battery$"],
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.entity_registry.async_get",
        return_value=mock_ent_reg,
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.device_registry.async_get",
        return_value=MagicMock(devices={}),
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.area_registry.async_get",
        return_value=MagicMock(async_list_areas=MagicMock(return_value=[])),
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.floor_registry.async_get",
        return_value=MagicMock(async_list_floors=MagicMock(return_value=[])),
    ):
        req = {
            "jsonrpc": "2.0",
            "id": 51,
            "method": "tools/call",
            "params": {
                "name": "get_entity",
                "arguments": {"entity_id": "sensor.blocked_battery"},
            },
        }
        res = await async_handle_mcp_payload(mock_hass, req)
        assert res["jsonrpc"] == "2.0"
        assert not res["result"].get("isError", False)
        ent = json.loads(res["result"]["content"][0]["text"])
        assert ent["entity_id"] == "sensor.blocked_battery"
        assert ent["blocklisted"] is True


@pytest.mark.asyncio
async def test_mcp_call_unknown_tool(mock_hass):
    """Test calling an unknown tool returns isError=True."""
    req = {
        "jsonrpc": "2.0",
        "id": 52,
        "method": "tools/call",
        "params": {"name": "unsupported_tool", "arguments": {}},
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == 52
    assert res["result"].get("isError") is True
    assert "not implemented or unknown" in res["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_call_invalid_arguments_type(mock_hass):
    """Test tools/call with invalid arguments type returns error -32602."""
    req = {
        "jsonrpc": "2.0",
        "id": 53,
        "method": "tools/call",
        "params": {"name": "list_entities", "arguments": "not-a-dict"},
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert "error" in res
    assert res["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_mcp_call_get_entity_missing_id(mock_hass):
    """Test get_entity with missing entity_id returns tool error."""
    req = {
        "jsonrpc": "2.0",
        "id": 54,
        "method": "tools/call",
        "params": {"name": "get_entity", "arguments": {}},
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert res["result"].get("isError") is True
    assert "Missing required argument" in res["result"]["content"][0]["text"]


# ===========================================================================
# Task 3: Mutation & Action Tool Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_mcp_call_set_entity_exposure(mock_hass):
    """Test set_entity_exposure successfully updates entity exposure."""
    import json

    req = {
        "jsonrpc": "2.0",
        "id": 20,
        "method": "tools/call",
        "params": {
            "name": "set_entity_exposure",
            "arguments": {"entity_ids": ["light.living_room_lights"], "exposed": True},
        },
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert not res["result"].get("isError", False)
    content = json.loads(res["result"]["content"][0]["text"])
    assert content["status"] == "success"
    assert content["updated"] == ["light.living_room_lights"]


@pytest.mark.asyncio
async def test_mcp_call_set_entity_exposure_string_coercion(mock_hass):
    """Test set_entity_exposure coerces single string entity_ids to list."""
    import json

    req = {
        "jsonrpc": "2.0",
        "id": 201,
        "method": "tools/call",
        "params": {
            "name": "set_entity_exposure",
            "arguments": {"entity_ids": "light.single_light", "exposed": False},
        },
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert not res["result"].get("isError", False)
    content = json.loads(res["result"]["content"][0]["text"])
    assert content["status"] == "success"
    assert content["updated"] == ["light.single_light"]


@pytest.mark.asyncio
async def test_mcp_call_set_entity_exposure_invalid_args(mock_hass):
    """Test set_entity_exposure errors on missing or invalid arguments."""
    # Missing entity_ids
    req1 = {
        "jsonrpc": "2.0",
        "id": 202,
        "method": "tools/call",
        "params": {
            "name": "set_entity_exposure",
            "arguments": {"exposed": True},
        },
    }
    res1 = await async_handle_mcp_payload(mock_hass, req1)
    assert res1["result"].get("isError") is True

    # Missing exposed boolean
    req2 = {
        "jsonrpc": "2.0",
        "id": 203,
        "method": "tools/call",
        "params": {
            "name": "set_entity_exposure",
            "arguments": {"entity_ids": ["light.test"]},
        },
    }
    res2 = await async_handle_mcp_payload(mock_hass, req2)
    assert res2["result"].get("isError") is True

    # Empty entity_ids list
    req3 = {
        "jsonrpc": "2.0",
        "id": 204,
        "method": "tools/call",
        "params": {
            "name": "set_entity_exposure",
            "arguments": {"entity_ids": [], "exposed": True},
        },
    }
    res3 = await async_handle_mcp_payload(mock_hass, req3)
    assert res3["result"].get("isError") is True
    assert "Argument 'entity_ids' must contain at least one entity ID" in res3["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_call_set_entity_nicknames(mock_hass):
    """Test set_entity_nicknames with replace, append, and remove modes."""
    import json
    from unittest.mock import MagicMock, patch

    mock_entry = MagicMock()
    mock_entry.entity_id = "light.living_room_lights"
    mock_entry.aliases = ["Old Name"]
    mock_ent_reg = MagicMock()
    mock_ent_reg.async_get.return_value = mock_entry

    with patch(
        "custom_components.google_assistant_entity_console.mcp.entity_registry.async_get",
        return_value=mock_ent_reg,
    ):
        # 1. Replace mode
        req = {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "set_entity_nicknames",
                "arguments": {
                    "entity_id": "light.living_room_lights",
                    "nicknames": ["Chandelier", "Main Lights"],
                    "mode": "replace",
                },
            },
        }
        res = await async_handle_mcp_payload(mock_hass, req)
        assert res["jsonrpc"] == "2.0"
        assert not res["result"].get("isError", False)
        content = json.loads(res["result"]["content"][0]["text"])
        assert content["nicknames"] == ["Chandelier", "Main Lights"]

        # 2. Append mode
        mock_entry.aliases = ["Chandelier", "Main Lights"]
        req_append = {
            "jsonrpc": "2.0",
            "id": 211,
            "method": "tools/call",
            "params": {
                "name": "set_entity_nicknames",
                "arguments": {
                    "entity_id": "light.living_room_lights",
                    "nicknames": ["Ceiling Fan Light", "Chandelier"],  # deduplicate
                    "mode": "append",
                },
            },
        }
        res_append = await async_handle_mcp_payload(mock_hass, req_append)
        assert not res_append["result"].get("isError", False)
        content_append = json.loads(res_append["result"]["content"][0]["text"])
        assert content_append["nicknames"] == ["Chandelier", "Main Lights", "Ceiling Fan Light"]

        # 3. Remove mode
        mock_entry.aliases = ["Chandelier", "Main Lights", "Ceiling Fan Light"]
        req_remove = {
            "jsonrpc": "2.0",
            "id": 212,
            "method": "tools/call",
            "params": {
                "name": "set_entity_nicknames",
                "arguments": {
                    "entity_id": "light.living_room_lights",
                    "nicknames": ["Chandelier"],
                    "mode": "remove",
                },
            },
        }
        res_remove = await async_handle_mcp_payload(mock_hass, req_remove)
        assert not res_remove["result"].get("isError", False)
        content_remove = json.loads(res_remove["result"]["content"][0]["text"])
        assert content_remove["nicknames"] == ["Main Lights", "Ceiling Fan Light"]


@pytest.mark.asyncio
async def test_mcp_call_set_entity_nicknames_errors(mock_hass):
    """Test set_entity_nicknames validation errors."""
    # Missing entity_id
    req1 = {
        "jsonrpc": "2.0",
        "id": 213,
        "method": "tools/call",
        "params": {
            "name": "set_entity_nicknames",
            "arguments": {"nicknames": ["Test"]},
        },
    }
    res1 = await async_handle_mcp_payload(mock_hass, req1)
    assert res1["result"].get("isError") is True

    # Missing nicknames
    req2 = {
        "jsonrpc": "2.0",
        "id": 214,
        "method": "tools/call",
        "params": {
            "name": "set_entity_nicknames",
            "arguments": {"entity_id": "light.test"},
        },
    }
    res2 = await async_handle_mcp_payload(mock_hass, req2)
    assert res2["result"].get("isError") is True

    # Invalid mode
    req3 = {
        "jsonrpc": "2.0",
        "id": 215,
        "method": "tools/call",
        "params": {
            "name": "set_entity_nicknames",
            "arguments": {
                "entity_id": "light.test",
                "nicknames": ["Test"],
                "mode": "invalid_mode",
            },
        },
    }
    res3 = await async_handle_mcp_payload(mock_hass, req3)
    assert res3["result"].get("isError") is True


@pytest.mark.asyncio
async def test_mcp_call_manage_blocklist_rule(mock_hass):
    """Test manage_blocklist_rule adds and removes patterns."""
    import json
    from unittest.mock import patch

    with patch(
        "custom_components.google_assistant_entity_console.mcp.async_load_blocklist",
        return_value=[],
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.async_save_blocklist",
    ) as mock_save:
        # Add rule
        req_add = {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {
                "name": "manage_blocklist_rule",
                "arguments": {"action": "add", "pattern": ".*_battery_level$"},
            },
        }
        res_add = await async_handle_mcp_payload(mock_hass, req_add)
        assert res_add["jsonrpc"] == "2.0"
        assert not res_add["result"].get("isError", False)
        content_add = json.loads(res_add["result"]["content"][0]["text"])
        assert content_add["status"] == "success"
        assert content_add["action"] == "add"
        assert ".*_battery_level$" in content_add["blocklist"]
        assert "affected_entities_count" in content_add
        mock_save.assert_called_once()

    # Remove rule
    with patch(
        "custom_components.google_assistant_entity_console.mcp.async_load_blocklist",
        return_value=[".*_battery_level$"],
    ), patch(
        "custom_components.google_assistant_entity_console.mcp.async_save_blocklist",
    ) as mock_save_remove:
        req_rem = {
            "jsonrpc": "2.0",
            "id": 221,
            "method": "tools/call",
            "params": {
                "name": "manage_blocklist_rule",
                "arguments": {"action": "remove", "pattern": ".*_battery_level$"},
            },
        }
        res_rem = await async_handle_mcp_payload(mock_hass, req_rem)
        assert not res_rem["result"].get("isError", False)
        content_rem = json.loads(res_rem["result"]["content"][0]["text"])
        assert content_rem["action"] == "remove"
        assert ".*_battery_level$" not in content_rem["blocklist"]
        mock_save_remove.assert_called_once()


@pytest.mark.asyncio
async def test_mcp_call_manage_blocklist_rule_invalid_regex(mock_hass):
    """Test manage_blocklist_rule rejects invalid regex pattern."""
    req = {
        "jsonrpc": "2.0",
        "id": 222,
        "method": "tools/call",
        "params": {
            "name": "manage_blocklist_rule",
            "arguments": {"action": "add", "pattern": "[invalid(regex"},
        },
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert res["result"].get("isError") is True
    assert "Invalid regular expression pattern" in res["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_call_manage_blocklist_rule_invalid_action(mock_hass):
    """Test manage_blocklist_rule rejects invalid action."""
    req = {
        "jsonrpc": "2.0",
        "id": 223,
        "method": "tools/call",
        "params": {
            "name": "manage_blocklist_rule",
            "arguments": {"action": "destroy", "pattern": ".*_battery$"},
        },
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["result"].get("isError") is True


@pytest.mark.asyncio
async def test_mcp_call_sync_to_google(mock_hass):
    """Test sync_to_google triggers runtime sync."""
    import json

    req = {
        "jsonrpc": "2.0",
        "id": 23,
        "method": "tools/call",
        "params": {"name": "sync_to_google", "arguments": {}},
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert not res["result"].get("isError", False)
    content = json.loads(res["result"]["content"][0]["text"])
    assert content["status"] in ("success", "error")
    assert "status_code" in content
    assert "timestamp" in content


@pytest.mark.asyncio
async def test_mcp_call_top_level_exception_handling(mock_hass):
    """Test top-level try...except catches unhandled exceptions and returns isError."""
    from unittest.mock import patch

    with patch(
        "custom_components.google_assistant_entity_console.mcp._handle_set_entity_exposure",
        side_effect=RuntimeError("Simulated catastrophic crash"),
    ):
        req = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "set_entity_exposure",
                "arguments": {"entity_ids": ["light.test"], "exposed": True},
            },
        }
        res = await async_handle_mcp_payload(mock_hass, req)
        assert res["jsonrpc"] == "2.0"
        assert res["id"] == 99
        assert res["result"].get("isError") is True
        assert "Simulated catastrophic crash" in res["result"]["content"][0]["text"]


# ===========================================================================
# Task 4: Home Assistant HTTP View Integration (McpStreamableView) Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_mcp_view_attributes():
    """Test McpStreamableView URL, name, and auth requirement attributes."""
    view = McpStreamableView()
    assert view.url == "/api/google_assistant_entity_console/mcp"
    assert view.name == "api:google_assistant_entity_console:mcp"
    assert view.requires_auth is True


@pytest.mark.asyncio
async def test_mcp_view_post_json(mock_hass):
    """Test valid JSON-RPC POST returns 200 with Mcp-Protocol-Version header and JSON body."""
    import json

    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    app = web.Application()
    app["hass"] = mock_hass
    req = make_mocked_request(
        "POST",
        "/api/google_assistant_entity_console/mcp",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        app=app,
    )
    req._read_bytes = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode("utf-8")

    view = McpStreamableView()
    resp = await view.post(req)

    assert resp.status == 200
    assert resp.headers.get("Mcp-Protocol-Version") == "2026-07-28"
    assert resp.content_type == "application/json"
    body = json.loads(resp.body.decode("utf-8"))
    assert body == {"jsonrpc": "2.0", "id": 1, "result": {}}


@pytest.mark.asyncio
async def test_mcp_view_post_invalid_json(mock_hass):
    """Test invalid JSON POST returns HTTP 400 with -32700 parse error."""
    import json

    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    app = web.Application()
    app["hass"] = mock_hass
    req = make_mocked_request(
        "POST",
        "/api/google_assistant_entity_console/mcp",
        headers={"Content-Type": "application/json"},
        app=app,
    )
    req._read_bytes = b"invalid json content {"

    view = McpStreamableView()
    resp = await view.post(req)

    assert resp.status == 400
    assert resp.headers.get("Mcp-Protocol-Version") == "2026-07-28"
    body = json.loads(resp.body.decode("utf-8"))
    assert body.get("jsonrpc") == "2.0"
    assert body.get("error", {}).get("code") == -32700
    assert "Parse error" in body.get("error", {}).get("message", "")


@pytest.mark.asyncio
async def test_mcp_view_post_sse_stream(mock_hass):
    """Test Accept: text/event-stream returns 200 with SSE formatted event."""
    import json
    from unittest.mock import patch

    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    app = web.Application()
    app["hass"] = mock_hass
    req = make_mocked_request(
        "POST",
        "/api/google_assistant_entity_console/mcp",
        headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
        app=app,
    )
    req._read_bytes = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "2026-07-28"},
        }
    ).encode("utf-8")

    written_chunks = []
    orig_write = web.StreamResponse.write

    async def mock_write(self, data):
        written_chunks.append(data)
        return await orig_write(self, data)

    view = McpStreamableView()
    with patch.object(web.StreamResponse, "write", mock_write):
        resp = await view.post(req)

    assert resp.status == 200
    assert resp.headers.get("Content-Type") == "text/event-stream"
    assert resp.headers.get("Mcp-Protocol-Version") == "2026-07-28"
    assert resp.headers.get("Cache-Control") == "no-cache"
    assert resp.headers.get("Connection") == "keep-alive"

    assert len(written_chunks) == 1
    chunk_str = written_chunks[0].decode("utf-8")
    assert chunk_str.startswith("event: message\ndata: ")
    assert chunk_str.endswith("\n\n")

    event_payload = json.loads(chunk_str[len("event: message\ndata: ") : -2])
    assert event_payload["jsonrpc"] == "2.0"
    assert event_payload["id"] == 2
    assert event_payload["result"]["protocolVersion"] == "2026-07-28"


@pytest.mark.asyncio
async def test_mcp_view_post_notification_204(mock_hass):
    """Test JSON-RPC notification returns HTTP 204 No Content."""
    import json

    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    app = web.Application()
    app["hass"] = mock_hass
    req = make_mocked_request(
        "POST",
        "/api/google_assistant_entity_console/mcp",
        headers={"Content-Type": "application/json"},
        app=app,
    )
    req._read_bytes = json.dumps(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ).encode("utf-8")

    view = McpStreamableView()
    resp = await view.post(req)

    assert resp.status == 204
    assert resp.headers.get("Mcp-Protocol-Version") == "2026-07-28"


@pytest.mark.asyncio
async def test_mcp_view_post_internal_error(mock_hass):
    """Test unexpected exception in async_handle_mcp_payload returns HTTP 500 with -32603 internal error."""
    import json
    from unittest.mock import patch

    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    app = web.Application()
    app["hass"] = mock_hass
    req = make_mocked_request(
        "POST",
        "/api/google_assistant_entity_console/mcp",
        headers={"Content-Type": "application/json"},
        app=app,
    )
    req._read_bytes = json.dumps({"jsonrpc": "2.0", "id": 999, "method": "ping"}).encode("utf-8")

    view = McpStreamableView()
    with patch(
        "custom_components.google_assistant_entity_console.mcp.async_handle_mcp_payload",
        side_effect=RuntimeError("Database failure"),
    ):
        resp = await view.post(req)

    assert resp.status == 500
    assert resp.headers.get("Mcp-Protocol-Version") == "2026-07-28"
    body = json.loads(resp.body.decode("utf-8"))
    assert body.get("jsonrpc") == "2.0"
    assert body.get("id") == 999
    assert body.get("error", {}).get("code") == -32603
    assert "Internal error: Database failure" in body.get("error", {}).get("message", "")


@pytest.mark.asyncio
async def test_mcp_view_registration_in_setup_entry(mock_hass):
    """Test McpStreamableView is registered during async_setup_entry."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from custom_components.google_assistant_entity_console import async_setup_entry

    mock_entry = MagicMock()
    mock_hass.http.register_view = MagicMock()
    mock_hass.http.async_register_static_paths = AsyncMock()

    with patch(
        "custom_components.google_assistant_entity_console.async_remove_panel"
    ), patch(
        "custom_components.google_assistant_entity_console.async_register_built_in_panel"
    ), patch(
        "custom_components.google_assistant_entity_console.async_get_store",
        new_callable=AsyncMock,
    ), patch(
        "custom_components.google_assistant_entity_console.async_get_runtime",
        new_callable=AsyncMock,
    ), patch(
        "custom_components.google_assistant_entity_console.async_build_entity_config_map",
        new_callable=AsyncMock,
    ):
        result = await async_setup_entry(mock_hass, mock_entry)
        assert result is True

    registered_views = [
        call.args[0] for call in mock_hass.http.register_view.call_args_list
    ]
    assert any(isinstance(v, McpStreamableView) for v in registered_views)




