# Google Assistant Entity Console - Model Context Protocol (MCP) Server Design

**Date**: 2026-10-25  
**Component**: `google_assistant_entity_console`  
**Specification Version**: Model Context Protocol (MCP) `2026-07-28` (Streamable HTTP Transport)

---

## 1. Overview & Objectives

The **Google Assistant Entity Console** provides a native `.storage`-backed console for managing Home Assistant entity exposure, voice aliases/nicknames, regex blocklists, and zero-reboot `devices:requestSync` to Google HomeGraph.

This feature introduces a native **Model Context Protocol (MCP) Server** directly into the integration, allowing AI agents (such as Antigravity, Claude Desktop, Cursor, and Model Context Gateway / MCG) to inspect, configure, and synchronize Google Assistant devices via standard MCP tools.

### Key Objectives
* **Zero External Python Dependencies**: Built entirely upon Home Assistant's native HTTP engine (`aiohttp` via `HomeAssistantView`) without introducing third-party packages or risking dependency conflicts in HA Docker / Core.
* **Modern MCP Compliance (`2026-07-28`)**: Uses the stateless **Streamable HTTP** transport with a single unified POST endpoint, eliminating sticky sessions, protocol-level handshakes, and persistent SSE connection bottlenecks.
* **Seamless State Integration**: Connects directly to existing async runtime services (`runtime.py` and `store.py`) to reflect changes live in Home Assistant memory and Google HomeGraph without requiring restarts.
* **Secure by Default**: Protected by Home Assistant's authenticated HTTP pipeline (`requires_auth = True`), validating Long-Lived Access Tokens.

---

## 2. Architecture & Transport Specification

### 2.1 Endpoint
* **Path**: `/api/google_assistant_entity_console/mcp`
* **Method**: `POST`
* **Authentication**: Requires standard Home Assistant Long-Lived Access Token via `Authorization: Bearer <TOKEN>`.
* **View Name**: `api:google_assistant_entity_console:mcp`

### 2.2 Transport Protocol (Streamable HTTP - 2026-07-28)
In compliance with the 2026-07-28 revision:
* **Statelessness**: No protocol-level session initialization handshake or sticky connection tracking. Each HTTP POST request is self-contained.
* **Header Handling**:
  * Response header `Mcp-Protocol-Version: 2026-07-28` is included on all responses.
  * Respects `Mcp-Method` routing headers if provided by upstream proxies/gateways.
* **Response Framing**:
  * **Direct JSON (`application/json`)**: For standard, rapid requests (`tools/list`, `tools/call`, `ping`, `initialize`), the server responds directly with an `application/json` JSON-RPC 2.0 response object.
  * **Request-Scoped Streaming (`text/event-stream`)**: When requested via `Accept: text/event-stream` or for long-running operations, the server streams progress events and emits the final JSON-RPC response before terminating the HTTP stream.
* **Tool Caching**: Tool listing results advertise a `ttlMs: 300000` (5-minute cache hint), enabling clients and gateways to cache tool definitions safely.

---

## 3. Tool Registry & Schemas

The MCP server exposes 7 core tools covering inspection, entity configuration, blocklists, and cloud sync:

### 3.1 `list_entities`
Queries entities registered in Home Assistant along with their Google Assistant status.
* **Parameters**:
  * `domain` *(string, optional)*: Filter by domain (e.g. `light`, `switch`, `climate`).
  * `area` *(string, optional)*: Filter by area/room name or area ID.
  * `floor` *(string, optional)*: Filter by floor name or floor ID.
  * `exposure_status` *(string, optional, enum: `["all", "exposed", "not_exposed", "blocked"]`, default: `"all"`)*.
  * `search` *(string, optional)*: Text search across entity IDs, friendly names, and voice aliases.
* **Returns**: Array of entities with `entity_id`, `friendly_name`, `area`, `floor`, `domain`, `exposed`, `blocklisted`, `blocklist_rule`, and `nicknames`.

### 3.2 `get_entity`
Retrieves detailed Google Assistant configuration for a single entity.
* **Parameters**:
  * `entity_id` *(string, required)*: Target entity ID.
* **Returns**: Entity object with full exposure state, custom voice name, nicknames array, area/floor placement, and matched blocklist rule (if applicable).

### 3.3 `get_google_assistant_status`
Checks cloud project status, credentials state, and exposure counts.
* **Parameters**: None.
* **Returns**: `project_id`, `service_account_configured` (bool), `report_state` (bool), `exposed_count` (int), `blocklisted_count` (int), and `last_sync_timestamp`.

### 3.4 `set_entity_exposure`
Exposes or unexposes one or more entities to Google Assistant in `.storage` and memory.
* **Parameters**:
  * `entity_ids` *(array of strings, required)*: Entity ID(s) to modify.
  * `exposed` *(boolean, required)*: `true` to expose, `false` to exclude.
* **Returns**: Confirmation object with the list of modified entity IDs.

### 3.5 `set_entity_nicknames`
Modifies voice aliases used by Google Assistant for voice matching.
* **Parameters**:
  * `entity_id` *(string, required)*: Target entity ID.
  * `nicknames` *(array of strings, required)*: List of voice nickname strings.
  * `mode` *(string, optional, enum: `["replace", "append", "remove"]`, default: `"replace"`)*: Mutation mode.
* **Returns**: Updated active nickname array for the entity.

### 3.6 `manage_blocklist_rule`
Adds or removes a regular expression blocklist filter.
* **Parameters**:
  * `action` *(string, required, enum: `["add", "remove"]`)*: Action to perform.
  * `pattern` *(string, required)*: Regex pattern string (e.g. `.*_battery_level$`).
* **Returns**: Updated blocklist rules array and count of entities affected.

### 3.7 `sync_to_google`
Triggers real-time zero-reboot `devices:requestSync` to Google HomeGraph.
* **Parameters**: None.
* **Returns**: Sync result (`status`: `"success"` or `"error"`), HomeGraph HTTP status code, and timestamp.

---

## 4. Module & Integration Design

### 4.1 New File: `custom_components/google_assistant_entity_console/mcp.py`
Contains:
* `MCP_PROTOCOL_VERSION = "2026-07-28"`
* `TOOL_DEFINITIONS`: List of tool definitions conforming to JSON Schema draft-07 and MCP 2026-07-28 `ttlMs`.
* `async def handle_mcp_request(hass: HomeAssistant, payload: dict) -> dict`: Main JSON-RPC router.
* Tool implementation dispatchers invoking `async_get_store(hass)` and `async_get_runtime(hass)`.

### 4.2 Updates to `views.py`
Add `McpStreamableView(HomeAssistantView)`:
* Handles `POST` requests to `/api/google_assistant_entity_console/mcp`.
* Enforces `requires_auth = True`.
* Sets `Mcp-Protocol-Version: 2026-07-28` header.
* Dispatches to `handle_mcp_request`.

### 4.3 Updates to `__init__.py`
Register `hass.http.register_view(McpStreamableView())` within `async_setup_entry`.

---

## 5. Error Handling & Edge Cases

* **JSON-RPC Compliance**:
  * Code `-32700`: Parse error (invalid JSON).
  * Code `-32600`: Invalid Request.
  * Code `-32601`: Method not found.
  * Code `-32602`: Invalid params.
  * Code `-32603`: Internal error.
* **Tool-Level Errors**: Handled without crashing HTTP response by returning `{ "content": [{"type": "text", "text": "error description"}], "isError": true }`.
* **Invalid Regex Patterns**: Validated before adding to store using `re.compile()`; returns validation error if syntax is malformed.

---

## 6. Testing & Verification

* Create test harness in `tests/test_mcp.py`:
  * Verify `tools/list` returns the 7 tools with schemas and `ttlMs: 300000`.
  * Verify `tools/call` for each tool (`list_entities`, `get_entity`, `set_entity_exposure`, `set_entity_nicknames`, `manage_blocklist_rule`, `sync_to_google`, `get_google_assistant_status`).
  * Verify JSON-RPC error formats for malformed payloads and missing tool arguments.
  * Verify execution against mock Home Assistant instance with pytest.
