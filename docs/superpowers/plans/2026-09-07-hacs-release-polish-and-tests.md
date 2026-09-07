# HACS Release Polish & Non-Theatre Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish Google Assistant Entity Console for HACS and public release by toning down LLM-ified documentation, removing private hardcoded service account strings in YAML generation, and establishing a robust, non-theatre test suite runnable both locally and in Home Assistant Docker.

**Architecture:** Split tests into dedicated modules (`test_yaml.py`, `test_blocklist.py`, `test_entities.py`, `test_config_flow.py`, `test_views.py`) with a shared `conftest.py`. Update `views.py` `RebuildView` to dynamically extract and preserve existing YAML header keys while falling back to clean public placeholders. Review and tone down markdown documentation across the repository.

**Tech Stack:** Python 3.12/3.14, PyYAML, aiohttp, pytest, Home Assistant Core.

## Global Constraints

- Never commit or stage backend/frontend changes without verifying against the running Home Assistant Docker instance (`.agents/AGENTS.md`).
- Avoid "test theatre": every test must test real logic, edge cases, error codes, and assertions rather than purely mocking internal calls.
- Maintain documentation integrity while removing excessive emojis, analogies, and marketing hyperbole.

---

### Task 1: Test Infrastructure & Runner Setup (`tests/conftest.py`)

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_views.py`

**Interfaces:**
- Produces: `mock_hass`, `mock_entity_registry`, `mock_device_registry`, `mock_area_registry`, `mock_floor_registry` pytest fixtures.

- [ ] **Step 1: Write `tests/conftest.py`**
Define shared fixtures and minimal mock shims so tests can run cleanly when Home Assistant core is installed or shimmed.

- [ ] **Step 2: Run pytest to verify initial discovery**
Run: `PYTHONPATH=. pytest tests/test_views.py -v`
Expected: 13 passed in container / host.

- [ ] **Step 3: Commit**
```bash
git add tests/conftest.py
git commit -m "test: setup shared pytest fixtures in conftest.py"
```

---

### Task 2: Real YAML Serialization & Round-Trip Tests (`tests/test_yaml.py`)

**Files:**
- Create: `tests/test_yaml.py`

**Interfaces:**
- Tests: `Secret`, `Include`, `secret_representer`, `include_representer`, `load_yaml_exposed_entities`.

- [ ] **Step 1: Write failing tests in `tests/test_yaml.py`**
Test `!secret` and `!include` serialization via `yaml.dump(..., Dumper=yaml.SafeDumper)`. Test `load_yaml_exposed_entities` parsing real YAML with entity config entries, aliases, room names, and custom tags.

- [ ] **Step 2: Run test to verify it fails if behavior is broken**
Run: `PYTHONPATH=. pytest tests/test_yaml.py -v`

- [ ] **Step 3: Implement any required helpers if missing**
Verify representers and loader constructors operate without errors.

- [ ] **Step 4: Run test to verify it passes**
Run: `PYTHONPATH=. pytest tests/test_yaml.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**
```bash
git add tests/test_yaml.py
git commit -m "test: add real PyYAML serialization and loader roundtrip tests"
```

---

### Task 3: Dynamic YAML Header Preservation in `views.py`

**Files:**
- Modify: `custom_components/google_assistant_entity_console/views.py:351-470`
- Modify: `tests/test_yaml.py`

**Interfaces:**
- Produces: `extract_yaml_header(content: str) -> list[str]` helper in `views.py`.
- Preserves top-level keys (`project_id`, `service_account`, `report_state`, `secure_devices_pin`, `expose_by_default`) when rebuilding YAML instead of hardcoding `homeassistantdocker-3f199-994a25247393.json`.

- [ ] **Step 1: Write test for header preservation in `tests/test_yaml.py`**
Test that existing header lines are extracted and retained, while defaulting to standard placeholder values (`!include SERVICE_ACCOUNT.json`) when starting fresh.

- [ ] **Step 2: Run test to verify it fails**
Run: `PYTHONPATH=. pytest tests/test_yaml.py -k test_yaml_header -v`
Expected: FAIL.

- [ ] **Step 3: Update `RebuildView` in `views.py`**
Implement `extract_yaml_header` and integrate it into `RebuildView.post`.

- [ ] **Step 4: Run test to verify it passes**
Run: `PYTHONPATH=. pytest tests/test_yaml.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add custom_components/google_assistant_entity_console/views.py tests/test_yaml.py
git commit -m "fix(rebuild): dynamically preserve existing YAML header keys and remove private service account"
```

---

### Task 4: Regex Blocklist Engine Tests (`tests/test_blocklist.py`)

**Files:**
- Create: `tests/test_blocklist.py`
- Modify: `custom_components/google_assistant_entity_console/views.py` (if error handling needs hardening)

**Interfaces:**
- Tests: `load_blocklist`, `save_blocklist`, `BlocklistView.get`, `BlocklistView.post`, `BlocklistAddView.post`.

- [ ] **Step 1: Write comprehensive blocklist tests in `tests/test_blocklist.py`**
Include:
- Valid pattern persistence.
- Rejection of invalid regex patterns with 400 Bad Request.
- Entity ID pattern filtering against real sample entity lists.
- Quick add appending and duplicate suppression.

- [ ] **Step 2: Run test to verify behavior**
Run: `PYTHONPATH=. pytest tests/test_blocklist.py -v`

- [ ] **Step 3: Fix/harden blocklist views in `views.py` if invalid regex wasn't caught cleanly**

- [ ] **Step 4: Run test to verify it passes**
Run: `PYTHONPATH=. pytest tests/test_blocklist.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add tests/test_blocklist.py custom_components/google_assistant_entity_console/views.py
git commit -m "test: add comprehensive regex blocklist validation and persistence tests"
```

---

### Task 5: Real Entity Filtering, Grouping & Normalization Tests (`tests/test_entities.py`)

**Files:**
- Create: `tests/test_entities.py`

**Interfaces:**
- Tests: `async_fetch_entities_data`.

- [ ] **Step 1: Write tests for `async_fetch_entities_data`**
Test:
- Supported vs unsupported domain filtering.
- Device class filtering for binary sensors and sensors.
- Skipping hidden and disabled entities.
- Light group detection marking children with `is_group_member: True`.
- Regex blocklist exclusion during entity fetch.
- `COMPUTED_NAME` singleton fallback.

- [ ] **Step 2: Run test to verify it passes**
Run: `PYTHONPATH=. pytest tests/test_entities.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add tests/test_entities.py
git commit -m "test: add entity registry filtering, grouping, and device class validation tests"
```

---

### Task 6: Config Flow & Integration Lifecycle Tests (`tests/test_config_flow.py`)

**Files:**
- Create: `tests/test_config_flow.py`

**Interfaces:**
- Tests: `ConfigFlow.async_step_user`, `async_setup_entry`, `async_unload_entry`.

- [ ] **Step 1: Write config flow and lifecycle tests**
Test:
- User step shows form when empty.
- User step creates entry with title "Google Sync".
- Single instance abort when an entry already exists.
- Setup registers panel, views, and static path.
- Unload removes panel.

- [ ] **Step 2: Run test to verify it passes**
Run: `PYTHONPATH=. pytest tests/test_config_flow.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add tests/test_config_flow.py
git commit -m "test: add config flow and integration setup/unload tests"
```

---

### Task 7: View Endpoints & AI Parsing Tests (`tests/test_views.py`)

**Files:**
- Modify: `tests/test_views.py`

**Interfaces:**
- Tests: `UpdateEntityView`, `AISettingsView`, `AIModelsView`, `AIHaAgentsView`, `AIGenerateNicknamesView`, `AISuggestExposureView`, `AIGenerateSingleEntityNicknameView`.

- [ ] **Step 1: Update `tests/test_views.py`**
Ensure tests cover:
- Updating entity name, aliases (filtering out zeros/empty values), and exposure option.
- AI nickname parsing (handling trailing commas, spaces, punctuation).
- AI exposure suggestion JSON parsing (handling markdown code blocks ` ```json [...] ``` `).
- Error status codes when upstream LLM fails.

- [ ] **Step 2: Run test to verify it passes**
Run: `PYTHONPATH=. pytest tests/test_views.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add tests/test_views.py
git commit -m "test: enhance API view and AI parsing tests"
```

---

### Task 8: Documentation Polish (De-LLM-ification) & HACS Review

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/AI_INTEGRATION.md`
- Modify: `docs/THEMING.md`
- Modify: `docs/COMMUNITY_POSTS.md`
- Check: `hacs.json`, `custom_components/google_assistant_entity_console/manifest.json`

- [ ] **Step 1: Polish `README.md`**
Remove marketing buzzwords, analogies, and excessive emojis while keeping clear technical instructions and screenshots.

- [ ] **Step 2: Polish `docs/ARCHITECTURE.md`**
Simplify tree descriptions, remove LaTeX formulas for hierarchy, keep Mermaid diagram and API tables accurate.

- [ ] **Step 3: Polish `docs/AI_INTEGRATION.md` and `docs/THEMING.md`**
Ensure factual technical language, explain endpoints, prompts, and CSS variable mapping cleanly.

- [ ] **Step 4: Commit documentation changes**
```bash
git add README.md docs/
git commit -m "docs: refine documentation tone, eliminate analogies and excessive emojis for HACS release"
```

---

### Task 9: Live Home Assistant Docker Verification & Cleanup

**Files:**
- Deploy to: `/ha/823SCD-Docker/custom_components/google_assistant_entity_console/`
- Deploy to: `/ha/823SCD-Docker/tests/`

- [ ] **Step 1: Copy updated custom component and tests to running HA instance**
- [ ] **Step 2: Run full test suite inside the container**
Run: `docker exec -w /config -e PYTHONPATH=. homeassistant pytest tests/ -v`
Expected: 100% of tests pass.

- [ ] **Step 3: Verify Home Assistant container logs for zero errors**
Run: `docker logs --tail 100 homeassistant | grep -i google_assistant_entity_console || true`

- [ ] **Step 4: Final git status check and verification**
Ensure working directory is clean and all commits are properly tracked.
