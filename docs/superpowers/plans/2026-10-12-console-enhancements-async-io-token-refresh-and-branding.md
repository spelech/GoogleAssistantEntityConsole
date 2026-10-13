# Console Enhancements, Async I/O, Token Refresh, and Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize Google Assistant Entity Console with non-blocking async file I/O, auto-refreshing authentication tokens, missing YAML include guidance, clean developer tooling (`pyproject.toml` and ruff), and a new Google-colored Home Assistant brand logo.

**Architecture:** Refactor synchronous file I/O in `views.py` to use `hass.async_add_executor_job`, introduce bidirectional `postMessage` synchronization between `panel.js` and `app.js` for token resilience, detect missing `!include` directives in `configuration.yaml` during rebuilds with interactive UI guidance, set up standardized `pyproject.toml`, and generate SVG/PNG logo assets applying Google Assistant's 4-color palette to the Home Assistant network graph.

**Tech Stack:** Python 3.12, Home Assistant custom components (`aiohttp`, `homeassistant.core`, `homeassistant.components.frontend`), PyYAML, pytest, pytest-asyncio, Ruff, Vanilla JavaScript (ES6+), SVG / Pillow (Python imaging).

## Global Constraints

- Preserve all existing file paths (`configuration.yaml`, `gaGen_*.yaml`, `google_assistant_entity_console_*.json`).
- Zero blocking file I/O on the Home Assistant main event loop.
- All 336 existing unit tests must continue to pass.
- Code must pass `ruff check .` with zero errors.
- Both repository files (`/drives/nfs/repos/google-assistant-entity-console`) and HA container files (`/ha/823SCD-Docker/custom_components/google_assistant_entity_console`) must remain in sync.

---

### Task 1: Developer Tooling (`pyproject.toml`) and Conftest Cleanups

**Files:**
- Create: `pyproject.toml`
- Modify: `tests/conftest.py`
- Test: `tests/test_yaml.py`

**Interfaces:**
- Produces: `pyproject.toml` defining pytest root and pythonpath `["."]`, ruff target version py312.

- [ ] **Step 1: Create `pyproject.toml`**

Write `pyproject.toml` in repository root:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "strict"

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "SIM"]
ignore = ["E501", "B008", "SIM108"]
```

- [ ] **Step 2: Fix `tests/conftest.py` mutable class attribute**

Update line 137 in `tests/conftest.py`:
Change `extra_urls = []` inside class definition to initialize `self.extra_urls = []` in `__init__` or annotate as `ClassVar`.

- [ ] **Step 3: Run pytest directly without `PYTHONPATH=.`**

Run: `pytest`  
Expected: 336 passed in ~1.5s.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/conftest.py
git commit -m "chore: add pyproject.toml and fix conftest mutable class attribute"
```

---

### Task 2: Non-Blocking Async File I/O in `views.py`

**Files:**
- Modify: `custom_components/google_assistant_entity_console/views.py`
- Test: `tests/test_blocklist.py`, `tests/test_views.py`, `tests/test_yaml.py`

**Interfaces:**
- Consumes: `hass.async_add_executor_job`
- Produces: Async helper functions `async_load_blocklist`, `async_save_blocklist`, `async_load_ai_settings`, `async_save_ai_settings`, non-blocking `RebuildView.post`.

- [ ] **Step 1: Write tests for async file helpers**

Add test cases in `tests/test_blocklist.py` verifying that blocklist read/write operations execute asynchronously without blocking the event loop and preserve JSON contents.

- [ ] **Step 2: Implement file helper functions in `views.py`**

Define:
```python
def _sync_read_json(filepath: str, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception as err:
        _LOGGER.error("Failed to load JSON from %s: %s", filepath, err)
        return default

def _sync_write_json(filepath: str, data) -> None:
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as err:
        _LOGGER.error("Failed to save JSON to %s: %s", filepath, err)

def _sync_write_file(filepath: str, content: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
```

Update `load_blocklist` and `save_blocklist`, `load_ai_settings` and `save_ai_settings` to support both async and sync execution (or convert views to await executor job). In views (`BlocklistView`, `BlocklistAddView`, `AISettingsView`, `RebuildView`, `EntitiesView`), await the executor job so file I/O does not stall the loop.

- [ ] **Step 3: Run pytest to verify all existing and new tests pass**

Run: `pytest`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add custom_components/google_assistant_entity_console/views.py tests/
git commit -m "perf: offload file I/O to executor jobs in views.py"
```

---

### Task 3: Missing YAML Include Detection in Backend and UI

**Files:**
- Modify: `custom_components/google_assistant_entity_console/views.py`
- Modify: `custom_components/google_assistant_entity_console/static/app.js`
- Modify: `custom_components/google_assistant_entity_console/static/index.html`
- Test: `tests/test_yaml.py`

**Interfaces:**
- Produces: `RebuildView` JSON response fields: `has_include_directive: bool`, `required_include: str`.

- [ ] **Step 1: Write test for missing include directive in `tests/test_yaml.py`**

Test that when `configuration.yaml` does not have `google_assistant: !include ...`, `RebuildView` returns `has_include_directive: false` and the snippet string.

- [ ] **Step 2: Update `RebuildView.post` in `views.py`**

```python
has_include = bool(re.search(include_pattern, config_content))
if has_include:
    # replace with filename
...
return self.json({
    "success": True,
    "has_include_directive": has_include,
    "required_include": f"google_assistant: !include {filename}",
    "exposed_count": exposed_count,
    "yaml_written": filepath
})
```

- [ ] **Step 3: Update `handleRebuild` in `app.js` and add missing include dialog in `index.html`**

When `result.has_include_directive === false`, display a highlighted banner in the modal showing the required snippet with a "Copy Snippet" button.

- [ ] **Step 4: Run pytest**

Run: `pytest tests/test_yaml.py`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/google_assistant_entity_console/ tests/test_yaml.py
git commit -m "feat: add missing configuration.yaml include detection and UI snippet copy"
```

---

### Task 4: Dynamic Auth Token Refresh in `panel.js` and `app.js`

**Files:**
- Modify: `custom_components/google_assistant_entity_console/static/panel.js`
- Modify: `custom_components/google_assistant_entity_console/static/app.js`

**Interfaces:**
- `panel.js` posts `{ type: "HA_TOKEN_UPDATE", token: string }`
- `app.js` listens for `HA_TOKEN_UPDATE` and posts `{ type: "REQUEST_HA_TOKEN" }` upon 401.

- [ ] **Step 1: Update `panel.js`**

Implement `this._hass = hass` and postMessage dispatch on token change:
```javascript
if (this._iframe && this._iframe.contentWindow && hass.auth && hass.auth.accessToken) {
  this._iframe.contentWindow.postMessage({
    type: "HA_TOKEN_UPDATE",
    token: hass.auth.accessToken
  }, "*");
}
```
Add message event listener for `REQUEST_HA_TOKEN`.

- [ ] **Step 2: Update `app.js`**

Add message listener for `HA_TOKEN_UPDATE`. Wrap `fetch` calls in an authenticated fetch wrapper `apiFetch(url, options)` that detects 401 responses, requests a token update from parent window, and retries once.

- [ ] **Step 3: Commit**

```bash
git add custom_components/google_assistant_entity_console/static/panel.js custom_components/google_assistant_entity_console/static/app.js
git commit -m "feat: add automatic auth token synchronization and 401 retry handling"
```

---

### Task 5: Brand & App Logo Redesign (Google Colors on Home Assistant Logo)

**Files:**
- Create: `brand/logo.svg`
- Update: `brand/logo.png`
- Update: `brand/icon.png`
- Update: `custom_components/google_assistant_entity_console/static/logo.png`

**Interfaces:**
- SVG and PNGs depicting the Home Assistant house network graph with Google Assistant colors:
  - Blue: `#4285F4`
  - Red: `#EA4335`
  - Yellow: `#FBBC05`
  - Green: `#34A853`

- [ ] **Step 1: Create master vector `brand/logo.svg`**

Craft the Home Assistant geometric house network outline and internal nodes using Google Assistant colors with modern styling.

- [ ] **Step 2: Generate PNG exports**

Use Python with Pillow / Cairo / resvg or svg2png script to render crisp transparent 1024x1024 PNGs for `brand/logo.png`, `brand/icon.png`, and a 256x256 asset for `custom_components/google_assistant_entity_console/static/logo.png`.

- [ ] **Step 3: Verify image outputs**

Verify dimensions, transparency, and visual quality.

- [ ] **Step 4: Commit**

```bash
git add brand/ custom_components/google_assistant_entity_console/static/logo.png
git commit -m "style: redesign brand and app logo with Google Assistant colors on HA house graph"
```

---

### Task 6: Ruff Cleanups, Full Verification, and Container Sync

**Files:**
- Modify: `custom_components/google_assistant_entity_console/views.py`
- Modify: `tests/`
- Target: `/ha/823SCD-Docker/custom_components/google_assistant_entity_console/`

- [ ] **Step 1: Clean up remaining Ruff warnings**

Remove unused variables in `views.py` (lines 853-855, 917-919). Format test imports and combine nested `with` statements.
Run `ruff check .`  
Expected: 0 errors.

- [ ] **Step 2: Run full test suite**

Run `pytest`  
Expected: All tests pass.

- [ ] **Step 3: Synchronize changes to Home Assistant Docker directory**

Copy updated component files to `/ha/823SCD-Docker/custom_components/google_assistant_entity_console/`.

- [ ] **Step 4: Commit and finalize**

```bash
git add -A
git commit -m "chore: clean up linter warnings and finalize v1.7.1 release polish"
```
