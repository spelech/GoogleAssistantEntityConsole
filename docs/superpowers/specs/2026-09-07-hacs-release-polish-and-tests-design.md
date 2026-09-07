# Design Specification: HACS Polish, Documentation Tone & Non-Theatre Testing

- **Date**: 2026-09-07
- **Status**: Approved
- **Repository**: `spelech/googleAssistantConfigGen` (Google Assistant Entity Console)

---

## 1. Objective

Polish the repository for HACS submission and public release by:
1. Toning down marketing hyperbole, analogies, and excessive emojis in documentation to present clean, professional, and factual technical documentation.
2. Eliminating private hardcoded references in the YAML rebuild engine (`views.py`), dynamically preserving existing user headers or providing standard placeholders.
3. Replacing shallow, theatrical mock tests with a modular, rigorous test suite verifying real PyYAML serialization, regex blocklist logic, entity registry filtering/grouping, and config flow lifecycles.

---

## 2. Documentation Polish (De-LLM-ification)

### Target Files
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/AI_INTEGRATION.md`
- `docs/THEMING.md`
- `docs/COMMUNITY_POSTS.md`

### Tone Guidelines
- Remove conversational AI tropes, marketing buzzwords, and analogies (e.g. "replaces YAML friction with an elegant panel", "seamlessly blends", "frictionless").
- Keep emojis tasteful and minimal rather than using them decoratively on every bullet point or header.
- Maintain technical precision: describe components, API endpoints, registries, and configuration tags clearly.
- In `docs/ARCHITECTURE.md`, simplify unnecessary LaTeX math blocks representing tree hierarchies into clear text diagrams/lists.

---

## 3. Code Polish for Public Release

### Dynamic YAML Header Preservation (`views.py`)
- **Current Issue**: `views.py:372-378` hardcodes a user-specific filename:
  ```python
  service_account: !include homeassistantdocker-3f199-994a25247393.json
  ```
- **Resolution**:
  - Implement a header preservation parser in `RebuildView`: if an existing `gaGen_*.yaml` is found, read all top-level keys before `entity_config:` (such as `project_id`, `service_account`, `report_state`, `secure_devices_pin`, `expose_by_default`) and preserve them verbatim.
  - If no existing file exists, default to clean public placeholders:
    ```yaml
    project_id: !secret googleassistant_projectName
    service_account: !include SERVICE_ACCOUNT.json
    report_state: true
    expose_by_default: false
    entity_config:
    ```

### Manifest & HACS Compliance
- Ensure `manifest.json` and `hacs.json` adhere to HACS specifications:
  - Validate JSON formatting.
  - Confirm keys (`name`, `render_readme`, `homeassistant`, `iot_class`, `version`, `codeowners`, `issue_tracker`).

---

## 4. Non-Theatre Test Suite

The test suite will be restructured into modular, dedicated test files under `tests/`:

### 4.1 `tests/test_yaml.py` — YAML Generation & Parsing
- **Custom Representers & Loaders**:
  - Test `Secret` and `Include` representers with `yaml.dump(..., Dumper=yaml.SafeDumper)`.
  - Test `CustomLoader` handling `!secret` and `!include` scalar nodes without exceptions.
- **Header Extraction**:
  - Test header preservation from an existing file.
  - Test fallback defaults when creating a new YAML file.
- **Round-Trip Integrity**:
  - Write and re-read realistic `gaGen_*.yaml` configs containing exposed entities, aliases, rooms, and grouping comments.
- **Syntax Error Detection**:
  - Verify that invalid YAML syntax raises an explicit error and does not overwrite valid files.

### 4.2 `tests/test_blocklist.py` — Regex Blocklist Logic
- **Regex Compilation & Matching**:
  - Test valid patterns matching target entities (`.*_battery_level$`, `sensor\.weather_.*`, `^media_player\.`).
  - Test non-matching entities remaining visible.
- **Invalid Pattern Rejection**:
  - Test POST to `/api/google_assistant_entity_console/blocklist` with malformed regex (e.g. `[unclosed`, `*dangling`), verifying HTTP 400 response with descriptive error message.
- **Persistence & Mutation**:
  - Test `load_blocklist` and `save_blocklist` with file existence and non-existence.
  - Test `/api/google_assistant_entity_console/blocklist/add` endpoint appends patterns and avoids duplicate entries.

### 4.3 `tests/test_entities.py` — Entity Filtering & Normalization
- **Supported Domains**:
  - Verify supported domains (`light`, `switch`, `climate`, `lock`, `cover`, `fan`, `vacuum`, `media_player`, `alarm_control_panel`, `camera`, `scene`, `script`, `select`, `input_boolean`).
  - Verify rejection of unsupported domains (e.g. `automation`, `zone`, `sun`, `weather`).
- **Binary Sensor / Sensor Device Classes**:
  - Test allowed device classes (`door`, `window`, `smoke`, `temperature`, `humidity`, etc.) are retained.
  - Test disallowed device classes are filtered out.
- **Hidden & Disabled Filtering**:
  - Ensure entities with `disabled_by` or `hidden_by` are excluded.
- **Light Groups & Members**:
  - Test that entities listed in a group's `entity_id` attribute have `is_group_member: True`.
- **Computed Name Sentinel**:
  - Verify fallback behavior when entity name is Home Assistant's `COMPUTED_NAME` singleton or None.

### 4.4 `tests/test_config_flow.py` & Lifecycle
- **Config Flow**:
  - Test `async_step_user` presenting the form when no entry is configured.
  - Test entry creation (`title="Google Sync"`).
  - Test aborting with `single_instance_allowed` when an entry already exists.
- **Setup & Unload**:
  - Test `async_setup_entry` registers static path, HTTP views, and built-in panel.
  - Test `async_unload_entry` removes the custom panel.

### 4.5 `tests/test_views.py` — View Endpoints & AI Parsing
- **Update Entity**:
  - Test updating display name, aliases (filtering out zeros/empty strings), and conversation options.
- **AI Endpoints & Response Parsing**:
  - Test parsing comma-separated nickname strings into clean lists.
  - Test extracting JSON array from LLM responses, including markdown code block wrapping (` ```json [...] ``` `).
  - Test error handling for HTTP failures, timeouts, and malformed LLM outputs.

### 4.6 Test Harness & Running Environment
- Create `tests/conftest.py` providing mock Home Assistant fixtures so developers and CI can run `pytest tests/` directly without requiring full container setup.
- Verify that 100% of tests pass both via standard `pytest` and inside the running Home Assistant container:
  ```bash
  docker exec -w /config -e PYTHONPATH=. homeassistant pytest tests/
  ```

---

## 5. Verification Plan

1. Run `pytest` locally on the repository.
2. Sync modified component and tests to `/ha/823SCD-Docker/` and run `docker exec -w /config -e PYTHONPATH=. homeassistant pytest tests/`.
3. Verify running Home Assistant logs have no errors or warnings associated with `google_assistant_entity_console`.
4. Ensure git diff contains only clean, intentional changes.
