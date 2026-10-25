"""Tests for MCP server protocol dispatcher, schemas, and lifecycle."""

from __future__ import annotations

import pytest

from custom_components.google_assistant_entity_console.mcp import (
    MCP_PROTOCOL_VERSION,
    TOOL_DEFINITIONS,
    async_handle_mcp_payload,
)


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
