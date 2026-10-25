# Google Assistant Entity Console - MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a native Model Context Protocol (MCP) Server in Google Assistant Entity Console adhering to the 2026-07-28 Streamable HTTP specification to allow AI agents and Model Context Gateway (MCG) to inspect, configure, and synchronize Google Assistant devices.

**Architecture:** A lightweight, zero-dependency async JSON-RPC 2.0 dispatcher in `mcp.py` backed by `HomeAssistantView` in `views.py` mounted at `/api/google_assistant_entity_console/mcp`. Tool calls directly invoke existing async services in `runtime.py` and `store.py` for live zero-reboot updates and HomeGraph sync.

**Tech Stack:** Python 3.12+, Home Assistant Core / `aiohttp.web`, JSON-RPC 2.0, MCP Spec `2026-07-28`.

## Global Constraints

- Specification Version: Model Context Protocol (MCP) `2026-07-28` (Streamable HTTP Transport).
- Zero external dependencies: `requirements: []` in `manifest.json`.
- Authentication: Standard Home Assistant Long-Lived Access Token via `Authorization: Bearer <TOKEN>` (`requires_auth = True`).
- Endpoint: `POST /api/google_assistant_entity_console/mcp`.
- Protocol Version Header: `Mcp-Protocol-Version: 2026-07-28`.
- Tool Cache Hint: `ttlMs: 300000` (5 minutes) in `tools/list`.

---

### Task 1: Protocol Dispatcher, Schemas & Lifecycle in `mcp.py`

**Files:**
- Create: `custom_components/google_assistant_entity_console/mcp.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Consumes: Standard Python `json`, `typing`, and Home Assistant `HomeAssistant` type.
- Produces:
  - `MCP_PROTOCOL_VERSION = "2026-07-28"`
  - `TOOL_DEFINITIONS: list[dict]`
  - `async def async_handle_mcp_payload(hass: HomeAssistant, payload: dict) -> dict`

- [ ] **Step 1: Write failing tests for JSON-RPC dispatcher, initialize, ping, and tools/list**

```python
# In tests/test_mcp.py
import pytest
from custom_components.google_assistant_entity_console.mcp import (
    MCP_PROTOCOL_VERSION,
    TOOL_DEFINITIONS,
    async_handle_mcp_payload,
)

@pytest.mark.asyncio
async def test_mcp_protocol_version():
    assert MCP_PROTOCOL_VERSION == "2026-07-28"

@pytest.mark.asyncio
async def test_mcp_ping(mock_hass):
    req = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res == {"jsonrpc": "2.0", "id": 1, "result": {}}

@pytest.mark.asyncio
async def test_mcp_initialize(mock_hass):
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
async def test_mcp_tools_list(mock_hass):
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
    req = {"id": 4, "method": "unknown_method"}
    res = await async_handle_mcp_payload(mock_hass, req)
    assert "error" in res
    assert res["error"]["code"] == -32600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp.py -v`
Expected: FAIL with ModuleNotFoundError or import error for `mcp.py`.

- [ ] **Step 3: Implement `mcp.py` core dispatcher, tool schemas, and error handling**

Create `custom_components/google_assistant_entity_console/mcp.py` implementing:
- `MCP_PROTOCOL_VERSION = "2026-07-28"`
- `TOOL_DEFINITIONS` listing all 7 tool schemas with inputSchema and parameters.
- `async_handle_mcp_payload(hass: HomeAssistant, payload: dict) -> dict` handling `ping`, `initialize`, `notifications/initialized`, `tools/list`, and JSON-RPC errors (`-32600`, `-32601`, `-32602`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mcp.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/google_assistant_entity_console/mcp.py tests/test_mcp.py
git commit -m "feat(mcp): add 2026-07-28 protocol dispatcher and tool definitions"
```

---

### Task 2: Inspection Tools (`list_entities`, `get_entity`, `get_google_assistant_status`)

**Files:**
- Modify: `custom_components/google_assistant_entity_console/mcp.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Consumes:
  - `views.async_fetch_entities_data(hass)`
  - `store.async_get_store(hass)`
- Produces:
  - `tools/call` execution for `list_entities`, `get_entity`, and `get_google_assistant_status`.

- [ ] **Step 1: Write failing tests for inspection tools**

```python
# In tests/test_mcp.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp.py -k "test_mcp_call" -v`
Expected: FAIL (tool dispatcher not yet implemented for these tools).

- [ ] **Step 3: Implement inspection tool handlers in `mcp.py`**

Connect `list_entities`, `get_entity`, and `get_google_assistant_status` to `async_fetch_entities_data(hass)` and `async_get_store(hass)`. Add filtering logic for domain, area, floor, exposure_status, and search text.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mcp.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/google_assistant_entity_console/mcp.py tests/test_mcp.py
git commit -m "feat(mcp): implement list_entities, get_entity, and get_status tools"
```

---

### Task 3: Mutation & Control Tools (`set_entity_exposure`, `set_entity_nicknames`, `manage_blocklist_rule`, `sync_to_google`)

**Files:**
- Modify: `custom_components/google_assistant_entity_console/mcp.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Consumes:
  - `store.async_get_store(hass)`
  - `runtime.async_get_runtime(hass)`
  - `views.async_build_entity_config_map(hass)`
- Produces:
  - `tools/call` execution for `set_entity_exposure`, `set_entity_nicknames`, `manage_blocklist_rule`, and `sync_to_google`.

- [ ] **Step 1: Write failing tests for mutation tools**

```python
# In tests/test_mcp.py
@pytest.mark.asyncio
async def test_mcp_call_set_entity_exposure(mock_hass):
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

@pytest.mark.asyncio
async def test_mcp_call_set_entity_nicknames(mock_hass):
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

@pytest.mark.asyncio
async def test_mcp_call_manage_blocklist_rule(mock_hass):
    req = {
        "jsonrpc": "2.0",
        "id": 22,
        "method": "tools/call",
        "params": {
            "name": "manage_blocklist_rule",
            "arguments": {"action": "add", "pattern": ".*_battery_level$"},
        },
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert not res["result"].get("isError", False)

@pytest.mark.asyncio
async def test_mcp_call_sync_to_google(mock_hass):
    req = {
        "jsonrpc": "2.0",
        "id": 23,
        "method": "tools/call",
        "params": {"name": "sync_to_google", "arguments": {}},
    }
    res = await async_handle_mcp_payload(mock_hass, req)
    assert res["jsonrpc"] == "2.0"
    assert not res["result"].get("isError", False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp.py -k "test_mcp_call_set or test_mcp_call_manage or test_mcp_call_sync" -v`
Expected: FAIL.

- [ ] **Step 3: Implement mutation tools in `mcp.py`**

Wire tool handlers to:
- Update store entity settings & call `runtime.async_update_entity_config` without reboot.
- Manage regex patterns with regex validation (`re.compile`) and update store blocklist.
- Trigger `runtime.async_request_sync()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mcp.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/google_assistant_entity_console/mcp.py tests/test_mcp.py
git commit -m "feat(mcp): implement exposure, nicknames, blocklist, and sync tools"
```

---

### Task 4: Home Assistant HTTP View Integration (`McpStreamableView`)

**Files:**
- Modify: `custom_components/google_assistant_entity_console/views.py`
- Modify: `custom_components/google_assistant_entity_console/__init__.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Consumes: `mcp.async_handle_mcp_payload`
- Produces:
  - `McpStreamableView(HomeAssistantView)` at `/api/google_assistant_entity_console/mcp`
  - Integration registration in `async_setup_entry`

- [ ] **Step 1: Write failing tests for `McpStreamableView` endpoint**

```python
# In tests/test_mcp.py
from custom_components.google_assistant_entity_console.views import McpStreamableView

@pytest.mark.asyncio
async def test_mcp_view_post_json(mock_hass):
    view = McpStreamableView()
    # Mock aiohttp request with JSON payload
    # Verify response status 200, header Mcp-Protocol-Version: 2026-07-28, and JSON-RPC body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp.py -k "test_mcp_view" -v`
Expected: FAIL with ImportError (McpStreamableView does not exist).

- [ ] **Step 3: Implement `McpStreamableView` in `views.py` and register in `__init__.py`**

- In `views.py`:
  - Create `McpStreamableView(HomeAssistantView)` with `url = "/api/google_assistant_entity_console/mcp"`, `name = "api:google_assistant_entity_console:mcp"`, `requires_auth = True`.
  - Check `Accept` header for `text/event-stream` vs `application/json`.
  - Set `Mcp-Protocol-Version: 2026-07-28`.
- In `__init__.py`:
  - Import `McpStreamableView` and call `hass.http.register_view(McpStreamableView())`.

- [ ] **Step 4: Run tests to verify view passes**

Run: `pytest tests/test_mcp.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/google_assistant_entity_console/views.py custom_components/google_assistant_entity_console/__init__.py tests/test_mcp.py
git commit -m "feat(mcp): expose McpStreamableView at /api/google_assistant_entity_console/mcp"
```

---

### Task 5: Documentation & End-to-End Test Suite Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Test: Full test suite (`pytest tests/`)

- [ ] **Step 1: Update `README.md` and `docs/ARCHITECTURE.md`**

Add an **MCP Server (Model Context Protocol)** section explaining:
- Endpoint: `POST /api/google_assistant_entity_console/mcp`
- Authentication: Bearer token
- Spec version: `2026-07-28` (Streamable HTTP)
- List of tools and example client configuration (e.g. Model Context Gateway or Claude Desktop / Antigravity).

- [ ] **Step 2: Run entire test suite to guarantee 0 regressions**

Run: `pytest tests/`
Expected: All tests pass (including existing 361 tests and new test suite).

- [ ] **Step 3: Commit**

```bash
git add README.md docs/ARCHITECTURE.md
git commit -m "docs(mcp): document native MCP server endpoint and configuration"
```
