# .storage-Native & Zero-Reboot Google Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate `gaGen_*.yaml` generation, `configuration.yaml` requirements, and Home Assistant restarts by managing Google Assistant credentials and entity exposure 100% in Home Assistant's `.storage` and syncing live in memory via `GoogleConfig` and Google HomeGraph's `devices:requestSync` API.

**Architecture:** We introduce `ConsoleStore` (`store.py`) backed by `homeassistant.helpers.storage.Store` (`.storage/google_assistant_entity_console`) to persist Google credentials, last-synced entity metadata, blocklist patterns, and AI settings (with automatic first-run import from legacy YAML/JSON files). `GoogleAssistantRuntimeManager` (`runtime.py`) either attaches to an existing YAML-bootstrapped `GoogleConfig` instance or initializes HA Core's `GoogleConfig` + `GoogleAssistantView` directly from `.storage`, mutating `google_config._config["entity_config"]` in memory on every edit and invoking `await google_config.async_sync_entities_all()` on demand or via 15s debounced auto-sync.

**Tech Stack:** Python 3.12+, Home Assistant Core (`homeassistant.helpers.storage.Store`, `homeassistant.components.google_assistant.http.GoogleConfig`, `GoogleAssistantView`, `entity_registry`, `area_registry`), Vanilla ES6 JavaScript (`static/app.js`), HTML5/CSS3 (`static/index.html`, `static/style.css`), `pytest`, `pytest-asyncio`, `playwright`.

## Global Constraints

- **Zero Reboots:** Entity exposure, name, alias, room, and credential updates MUST take effect in memory immediately without calling `homeassistant.restart`.
- **100% `.storage` Persistence:** All integration data (`google_settings`, `synced_entities`, `blocklist`, `ai_settings`) MUST be stored in `.storage/google_assistant_entity_console` via `homeassistant.helpers.storage.Store(hass, 1, "google_assistant_entity_console")`.
- **Backwards Compatibility & Auto-Migration:** Existing `/config/google_assistant_entity_console_blocklist.json`, `/config/google_assistant_entity_console_ai_settings.json`, `/config/configuration.yaml`, `/config/secrets.yaml`, `/config/gaGen_*.yaml`, and `/config/SERVICE_ACCOUNT.json` MUST be auto-imported into `.storage` on first load if `.storage` is unpopulated.
- **Verification Rule:** All backend unit tests (`pytest`) and Playwright E2E tests (`tests/test_playwright_e2e.py`), plus verification against a running Home Assistant instance, MUST pass before merging to `main`.

---

## File Structure

- **Create:** `custom_components/google_assistant_entity_console/store.py`
  - `ConsoleStore`: Manages `.storage/google_assistant_entity_console` persistence, YAML/`!secret`/`!include` resolution, legacy JSON migration, and `comment_out_google_assistant_yaml()` helper.
- **Create:** `custom_components/google_assistant_entity_console/runtime.py`
  - `GoogleAssistantRuntimeManager`: Manages HA Core's `GoogleConfig` instance in `"yaml_attached"` or `"storage"` mode, builds live `entity_config` dicts from `core.entity_registry`, mutates `google_config._config` in memory, and triggers `async_sync_entities_all()`.
- **Modify:** `custom_components/google_assistant_entity_console/const.py`
  - Add storage constants (`STORAGE_KEY`, `STORAGE_VERSION`, `DATA_STORE`, `DATA_RUNTIME`).
- **Modify:** `custom_components/google_assistant_entity_console/__init__.py`
  - Initialize `ConsoleStore` and `GoogleAssistantRuntimeManager` in `async_setup_entry`, and register the new HTTP views (`SyncView`, `GoogleSettingsView`, `MigrateYamlView`).
- **Modify:** `custom_components/google_assistant_entity_console/views.py`
  - Refactor `async_fetch_entities_data`, `EntitiesView`, `UpdateEntityView`, `BlocklistView`, `BlocklistAddView`, and `AISettingsView` to use `ConsoleStore` and `GoogleAssistantRuntimeManager`.
  - Add `SyncView` (`/api/google_assistant_entity_console/sync`), `GoogleSettingsView` (`/api/google_assistant_entity_console/google_settings`), and `MigrateYamlView` (`/api/google_assistant_entity_console/migrate_yaml`). Keep `RebuildView` as a backwards-compatible alias to `SyncView`.
- **Modify:** `custom_components/google_assistant_entity_console/static/index.html`, `static/app.js`, `static/style.css`
  - Update header button from **Rebuild YAML** to **Sync to Google** (calling `/sync` without triggering `restartModal`).
  - Add **Google Assistant Connection (`.storage`)** configuration section and **Migrate from YAML** button inside the Settings modal.
- **Create:** `tests/test_store.py`
  - Unit tests for `ConsoleStore`, legacy JSON migration, YAML/`!secret`/`!include` auto-import, and `configuration.yaml` commenting out.
- **Create:** `tests/test_runtime.py`
  - Unit tests for `GoogleAssistantRuntimeManager` in both `"yaml_attached"` and `"storage"` modes, live `_config["entity_config"]` updates, and `async_sync_to_google()`.
- **Modify:** `tests/test_views.py`, `tests/test_blocklist.py`, `tests/test_entities.py`, `tests/test_playwright_e2e.py`
  - Update existing tests for `.storage`-backed views and add E2E tests for live sync and Google Connection settings.

---

### Task 1: Native `.storage` Store & Legacy YAML/JSON Auto-Migration (`store.py`)

**Files:**
- Modify: `custom_components/google_assistant_entity_console/const.py`
- Create: `custom_components/google_assistant_entity_console/store.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: `homeassistant.core.HomeAssistant`, `homeassistant.helpers.storage.Store`
- Produces:
  - `const.py`: `DOMAIN`, `STORAGE_KEY = "google_assistant_entity_console"`, `STORAGE_VERSION = 1`, `DATA_STORE = "store"`, `DATA_RUNTIME = "runtime"`
  - `store.py`:
    - `class ConsoleStore`:
      - `async def async_load(self) -> dict[str, Any]`
      - `async def async_save(self) -> None`
      - `property google_settings -> dict[str, Any]`
      - `async def async_update_google_settings(self, updates: dict[str, Any]) -> dict[str, Any]`
      - `property synced_entities -> dict[str, dict[str, Any]]`
      - `async def async_set_synced_entities(self, entities: dict[str, dict[str, Any]]) -> None`
      - `property blocklist -> list[str]`
      - `async def async_set_blocklist(self, patterns: list[str]) -> None`
      - `property ai_settings -> dict[str, Any]`
      - `async def async_set_ai_settings(self, settings: dict[str, Any]) -> None`
      - `async def async_has_legacy_yaml(self) -> bool`
      - `async def async_migrate_and_disable_yaml(self) -> dict[str, Any]`
    - `async def async_get_store(hass: HomeAssistant) -> ConsoleStore`

- [ ] **Step 1: Write the failing tests in `tests/test_store.py`**

```python
import json
import pytest
from unittest.mock import MagicMock
from custom_components.google_assistant_entity_console.store import ConsoleStore


@pytest.mark.asyncio
async def test_store_auto_migrates_legacy_files_and_yaml(tmp_path):
    """Test that ConsoleStore imports legacy JSON files, secrets.yaml, SERVICE_ACCOUNT.json, and gaGen YAML on first load."""
    # 1. Create legacy blocklist and AI settings JSON
    (tmp_path / "google_assistant_entity_console_blocklist.json").write_text(
        json.dumps([r"^sensor\.ignored_.*"]), encoding="utf-8"
    )
    (tmp_path / "google_assistant_entity_console_ai_settings.json").write_text(
        json.dumps({"ai_source": "home_assistant", "ha_agent_id": "conversation.gemini"}),
        encoding="utf-8",
    )

    # 2. Create secrets.yaml and SERVICE_ACCOUNT.json
    (tmp_path / "secrets.yaml").write_text(
        "googleassistant_projectName: my-home-project-123\ngoogle_device_pin: '4321'\n",
        encoding="utf-8",
    )
    service_account_data = {
        "type": "service_account",
        "project_id": "my-home-project-123",
        "client_email": "homegraph@my-home-project-123.iam.gserviceaccount.com",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC\n-----END PRIVATE KEY-----\n",
    }
    (tmp_path / "SERVICE_ACCOUNT.json").write_text(
        json.dumps(service_account_data), encoding="utf-8"
    )

    # 3. Create gaGen_101726.yaml and configuration.yaml
    (tmp_path / "gaGen_101726.yaml").write_text(
        "project_id: !secret googleassistant_projectName\n"
        "service_account: !include SERVICE_ACCOUNT.json\n"
        "report_state: true\n"
        "secure_devices_pin: !secret google_device_pin\n"
        "expose_by_default: false\n"
        "entity_config:\n"
        "  light.kitchen:\n"
        "    expose: true\n"
        "    name: Kitchen Light\n"
        "    aliases:\n"
        "      - Kitchen Lamp\n"
        "    room: Kitchen\n",
        encoding="utf-8",
    )
    (tmp_path / "configuration.yaml").write_text(
        "homeassistant:\n  name: Home\ngoogle_assistant: !include gaGen_101726.yaml\n",
        encoding="utf-8",
    )

    hass = MagicMock()
    hass.config.path.side_effect = lambda *parts: str(tmp_path.joinpath(*parts))
    async def async_add_executor_job(func, *args):
        return func(*args)
    hass.async_add_executor_job = async_add_executor_job

    store = ConsoleStore(hass)
    # Stub underlying HA Store load/save in memory
    saved_payloads = []
    async def fake_store_load():
        return saved_payloads[-1] if saved_payloads else None
    async def fake_store_save(data):
        saved_payloads.append(json.loads(json.dumps(data)))
    store._store.async_load = fake_store_load
    store._store.async_save = fake_store_save

    await store.async_load()

    assert store.blocklist == [r"^sensor\.ignored_.*"]
    assert store.ai_settings["ha_agent_id"] == "conversation.gemini"
    assert store.google_settings["project_id"] == "my-home-project-123"
    assert store.google_settings["secure_devices_pin"] == "4321"
    assert store.google_settings["report_state"] is True
    assert store.google_settings["service_account"]["client_email"] == "homegraph@my-home-project-123.iam.gserviceaccount.com"
    assert "light.kitchen" in store.synced_entities
    assert store.synced_entities["light.kitchen"]["name"] == "Kitchen Light"
    assert await store.async_has_legacy_yaml() is True

    # Test commenting out google_assistant in configuration.yaml
    mig_res = await store.async_migrate_and_disable_yaml()
    assert mig_res["commented_out"] is True
    assert await store.async_has_legacy_yaml() is False
    updated_conf = (tmp_path / "configuration.yaml").read_text(encoding="utf-8")
    assert "# google_assistant: !include gaGen_101726.yaml" in updated_conf
```

- [ ] **Step 2: Run `pytest tests/test_store.py` to verify it fails**

Run: `pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.google_assistant_entity_console.store'`

- [ ] **Step 3: Update `const.py` and implement `custom_components/google_assistant_entity_console/store.py`**

Update `custom_components/google_assistant_entity_console/const.py`:
```python
DOMAIN = "google_assistant_entity_console"
STORAGE_KEY = "google_assistant_entity_console"
STORAGE_VERSION = 1
DATA_STORE = "store"
DATA_RUNTIME = "runtime"
```

Create `custom_components/google_assistant_entity_console/store.py`:
```python
"""Native Home Assistant .storage manager for Google Assistant Entity Console."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DATA_STORE, DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

DEFAULT_GOOGLE_SETTINGS: dict[str, Any] = {
    "project_id": "",
    "service_account": {},
    "report_state": True,
    "secure_devices_pin": "",
    "auto_sync": False,
}


def _default_data() -> dict[str, Any]:
    return {
        "google_settings": copy.deepcopy(DEFAULT_GOOGLE_SETTINGS),
        "synced_entities": {},
        "blocklist": [],
        "ai_settings": {},
    }


def _sync_read_text(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as err:
        _LOGGER.warning("Could not read %s: %s", path, err)
        return None


def _sync_read_json(path: str, default: Any) -> Any:
    text = _sync_read_text(path)
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception as err:
        _LOGGER.warning("Could not parse JSON from %s: %s", path, err)
        return default


def _sync_load_secrets(config_dir_getter) -> dict[str, Any]:
    secrets_path = config_dir_getter("secrets.yaml")
    text = _sync_read_text(secrets_path)
    if not text:
        return {}
    try:
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except Exception as err:
        _LOGGER.warning("Failed to parse secrets.yaml: %s", err)
        return {}


def _sync_extract_yaml_import(config_dir_getter) -> dict[str, Any]:
    """Read configuration.yaml + included gaGen/google_assistant YAML and resolve !secret / !include."""
    config_path = config_dir_getter("configuration.yaml")
    config_text = _sync_read_text(config_path)
    if not config_text:
        return {}

    secrets = _sync_load_secrets(config_dir_getter)

    class ResolverLoader(yaml.SafeLoader):
        pass

    def _secret_ctor(loader, node):
        key = str(node.value).strip()
        return secrets.get(key, f"!secret {key}")

    def _include_ctor(loader, node):
        inc_file = str(node.value).strip()
        inc_path = config_dir_getter(inc_file)
        if inc_file.lower().endswith(".json"):
            return _sync_read_json(inc_path, {})
        inc_text = _sync_read_text(inc_path)
        if not inc_text:
            return {}
        return yaml.load(inc_text, Loader=ResolverLoader)

    ResolverLoader.add_constructor("!secret", _secret_ctor)
    ResolverLoader.add_constructor("!include", _include_ctor)

    # Check for `google_assistant: !include <file>` first so we don't fail on unrelated HA tags in configuration.yaml
    include_match = re.search(
        r"^[ \t]*google_assistant:\s*!include\s+([^\s#]+)",
        config_text,
         flags=re.MULTILINE,
    )
    ga_data: dict[str, Any] | None = None
    if include_match:
        inc_filename = include_match.group(1).strip()
        inc_text = _sync_read_text(config_dir_getter(inc_filename))
        if inc_text:
            try:
                loaded = yaml.load(inc_text, Loader=ResolverLoader)
                if isinstance(loaded, dict):
                    ga_data = loaded
            except Exception as err:
                _LOGGER.warning("Failed to parse included %s: %s", inc_filename, err)
    else:
        try:
            full_loaded = yaml.load(config_text, Loader=ResolverLoader)
            if isinstance(full_loaded, dict) and isinstance(full_loaded.get("google_assistant"), dict):
                ga_data = full_loaded["google_assistant"]
        except Exception:
            ga_data = None

    if not isinstance(ga_data, dict):
        return {}

    google_settings: dict[str, Any] = {}
    if project_id := ga_data.get("project_id"):
        if not str(project_id).startswith("!secret "):
            google_settings["project_id"] = str(project_id)
    if "report_state" in ga_data:
        google_settings["report_state"] = bool(ga_data.get("report_state"))
    if pin := ga_data.get("secure_devices_pin"):
        if not str(pin).startswith("!secret "):
            google_settings["secure_devices_pin"] = str(pin)
    if isinstance(ga_data.get("service_account"), dict):
        sa = ga_data["service_account"]
        if sa.get("client_email") and sa.get("private_key"):
            google_settings["service_account"] = sa

    synced_entities: dict[str, dict[str, Any]] = {}
    entity_cfg = ga_data.get("entity_config")
    if isinstance(entity_cfg, dict):
        for ent_id, cfg in entity_cfg.items():
            if isinstance(cfg, dict) and cfg.get("expose", False):
                synced_entities[str(ent_id)] = {
                    "name": cfg.get("name"),
                    "aliases": list(cfg.get("aliases") or []),
                    "room": cfg.get("room"),
                }

    return {
        "google_settings": google_settings,
        "synced_entities": synced_entities,
    }


def _sync_has_active_google_assistant_yaml(config_dir_getter) -> bool:
    config_text = _sync_read_text(config_dir_getter("configuration.yaml"))
    if not config_text:
        return False
    return bool(
        re.search(r"^[ \t]*google_assistant\s*:", config_text, flags=re.MULTILINE)
    )


def _sync_comment_out_google_assistant_yaml(config_dir_getter) -> bool:
    config_path = config_dir_getter("configuration.yaml")
    config_text = _sync_read_text(config_path)
    if not config_text:
        return False

    pattern = r"^([ \t]*)(google_assistant\s*:\s*!include\s+[^\r\n]+)"
    if re.search(pattern, config_text, flags=re.MULTILINE):
        updated = re.sub(
            pattern,
            r"\1# \2  # Migrated to .storage by Google Assistant Entity Console",
            config_text,
            flags=re.MULTILINE,
        )
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(updated)
        return True
    return False


class ConsoleStore:
    """Manage persistent .storage state for Google Assistant Entity Console."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._data: dict[str, Any] = _default_data()
        self._loaded = False

    async def async_load(self) -> dict[str, Any]:
        """Load store data and auto-migrate legacy files if needed."""
        stored = await self._store.async_load()
        dirty = False

        if not isinstance(stored, dict):
            stored = _default_data()
            dirty = True

        for k, default_val in _default_data().items():
            if k not in stored or not isinstance(stored[k], type(default_val)):
                stored[k] = copy.deepcopy(default_val)
                dirty = True

        for k, v in DEFAULT_GOOGLE_SETTINGS.items():
            if k not in stored["google_settings"]:
                stored["google_settings"][k] = copy.deepcopy(v)
                dirty = True

        # Migrate legacy blocklist JSON if store blocklist is empty
        if not stored["blocklist"]:
            legacy_bl = await self.hass.async_add_executor_job(
                _sync_read_json,
                self.hass.config.path("google_assistant_entity_console_blocklist.json"),
                [],
            )
            if isinstance(legacy_bl, list) and legacy_bl:
                stored["blocklist"] = [str(p) for p in legacy_bl if isinstance(p, str)]
                dirty = True

        # Migrate legacy AI settings JSON if store ai_settings is empty
        if not stored["ai_settings"]:
            legacy_ai = await self.hass.async_add_executor_job(
                _sync_read_json,
                self.hass.config.path("google_assistant_entity_console_ai_settings.json"),
                {},
            )
            if isinstance(legacy_ai, dict) and legacy_ai:
                stored["ai_settings"] = legacy_ai
                dirty = True

        # Auto-import from configuration.yaml / gaGen YAML if project_id or synced_entities is empty
        if not stored["google_settings"].get("project_id") or not stored["synced_entities"]:
            yaml_imported = await self.hass.async_add_executor_job(
                _sync_extract_yaml_import, self.hass.config.path
            )
            imported_gs = yaml_imported.get("google_settings") or {}
            for k, val in imported_gs.items():
                if val and not stored["google_settings"].get(k):
                    stored["google_settings"][k] = val
                    dirty = True
            imported_synced = yaml_imported.get("synced_entities") or {}
            if imported_synced and not stored["synced_entities"]:
                stored["synced_entities"] = imported_synced
                dirty = True

        self._data = stored
        self._loaded = True
        if dirty:
            await self.async_save()
        return self._data

    async def async_save(self) -> None:
        """Persist current data to .storage."""
        await self._store.async_save(self._data)

    @property
    def google_settings(self) -> dict[str, Any]:
        return self._data["google_settings"]

    async def async_update_google_settings(
        self, updates: dict[str, Any]
    ) -> dict[str, Any]:
        gs = self._data["google_settings"]
        if "project_id" in updates and updates["project_id"] is not None:
            gs["project_id"] = str(updates["project_id"]).strip()
        if "report_state" in updates and updates["report_state"] is not None:
            gs["report_state"] = bool(updates["report_state"])
        if "secure_devices_pin" in updates and updates["secure_devices_pin"] is not None:
            gs["secure_devices_pin"] = str(updates["secure_devices_pin"]).strip()
        if "auto_sync" in updates and updates["auto_sync"] is not None:
            gs["auto_sync"] = bool(updates["auto_sync"])
        if "service_account" in updates and updates["service_account"]:
            sa = updates["service_account"]
            if isinstance(sa, str):
                sa = json.loads(sa)
            if isinstance(sa, dict) and sa.get("client_email") and sa.get("private_key"):
                gs["service_account"] = sa
            else:
                raise ValueError("Service account JSON must contain 'client_email' and 'private_key'.")
        await self.async_save()
        return gs

    @property
    def synced_entities(self) -> dict[str, dict[str, Any]]:
        return self._data["synced_entities"]

    async def async_set_synced_entities(
        self, entities: dict[str, dict[str, Any]]
    ) -> None:
        self._data["synced_entities"] = {
            ent_id: {
                "name": cfg.get("name"),
                "aliases": list(cfg.get("aliases") or []),
                "room": cfg.get("room"),
            }
            for ent_id, cfg in entities.items()
        }
        await self.async_save()

    @property
    def blocklist(self) -> list[str]:
        return self._data["blocklist"]

    async def async_set_blocklist(self, patterns: list[str]) -> None:
        self._data["blocklist"] = list(patterns)
        await self.async_save()

    @property
    def ai_settings(self) -> dict[str, Any]:
        return self._data["ai_settings"]

    async def async_set_ai_settings(self, settings: dict[str, Any]) -> None:
        self._data["ai_settings"] = dict(settings)
        await self.async_save()

    async def async_has_legacy_yaml(self) -> bool:
        return await self.hass.async_add_executor_job(
            _sync_has_active_google_assistant_yaml, self.hass.config.path
        )

    async def async_migrate_and_disable_yaml(self) -> dict[str, Any]:
        """Import any remaining YAML settings and comment out google_assistant: in configuration.yaml."""
        yaml_imported = await self.hass.async_add_executor_job(
            _sync_extract_yaml_import, self.hass.config.path
        )
        imported_gs = yaml_imported.get("google_settings") or {}
        for k, val in imported_gs.items():
            if val and not self._data["google_settings"].get(k):
                self._data["google_settings"][k] = val
        imported_synced = yaml_imported.get("synced_entities") or {}
        if imported_synced and not self._data["synced_entities"]:
            self._data["synced_entities"] = imported_synced
        await self.async_save()

        commented_out = await self.hass.async_add_executor_job(
            _sync_comment_out_google_assistant_yaml, self.hass.config.path
        )
        return {
            "commented_out": commented_out,
            "project_id": self._data["google_settings"].get("project_id", ""),
        }


async def async_get_store(hass: HomeAssistant) -> ConsoleStore:
    """Get or initialize the singleton ConsoleStore in hass.data."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    store: ConsoleStore | None = domain_data.get(DATA_STORE)
    if store is None:
        store = ConsoleStore(hass)
        await store.async_load()
        domain_data[DATA_STORE] = store
    return store
```

- [ ] **Step 4: Run `pytest tests/test_store.py -v` to verify it passes**

Run: `pytest tests/test_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add custom_components/google_assistant_entity_console/const.py custom_components/google_assistant_entity_console/store.py tests/test_store.py
git commit -m "feat(store): add .storage ConsoleStore with automatic YAML and JSON migration"
```

---

### Task 2: Zero-Reboot Runtime Manager (`runtime.py`)

**Files:**
- Create: `custom_components/google_assistant_entity_console/runtime.py`
- Create: `tests/test_runtime.py`

**Interfaces:**
- Consumes:
  - `ConsoleStore` from `custom_components/google_assistant_entity_console/store.py`
  - `GoogleConfig`, `GoogleAssistantView` from `homeassistant.components.google_assistant.http`
  - `DATA_CONFIG`, `DEFAULT_EXPOSED_DOMAINS`, `DOMAIN as GA_DOMAIN`, `SERVICE_REQUEST_SYNC` from `homeassistant.components.google_assistant.const`
- Produces:
  - `class GoogleAssistantRuntimeManager`:
    - `mode: str` (`"storage"` | `"yaml_attached"` | `"unconfigured"`)
    - `google_config: GoogleConfig | None`
    - `async def async_initialize(self, entity_config: dict[str, dict[str, Any]]) -> None`
    - `async def async_refresh_memory_config(self, entity_config: dict[str, dict[str, Any]], schedule_auto_sync: bool = False) -> None`
    - `async def async_sync_to_google(self, entity_config: dict[str, dict[str, Any]]) -> dict[str, Any]`
    - `def get_status_summary(self) -> dict[str, Any]`
  - `async def async_get_runtime(hass: HomeAssistant) -> GoogleAssistantRuntimeManager`

- [ ] **Step 1: Write the failing unit tests in `tests/test_runtime.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.config_entries import ConfigEntryState
from custom_components.google_assistant_entity_console.runtime import (
    GoogleAssistantRuntimeManager,
)


@pytest.mark.asyncio
async def test_runtime_attaches_to_existing_yaml_google_config():
    """Verify runtime attaches to an active google_assistant ConfigEntry and mutates _config in place."""
    hass = MagicMock()
    hass.data = {}
    mock_google_config = MagicMock()
    mock_google_config._config = {"project_id": "yaml-proj", "entity_config": {}}
    mock_google_config.async_get_agent_users.return_value = {"agent-1": {}}
    mock_google_config.async_sync_entities_all = AsyncMock(return_value=200)
    mock_google_config.async_schedule_google_sync_all = MagicMock()

    mock_entry = MagicMock()
    mock_entry.state = ConfigEntryState.LOADED
    mock_entry.runtime_data = mock_google_config
    hass.config_entries.async_entries.return_value = [mock_entry]

    mock_store = MagicMock()
    mock_store.google_settings = {
        "project_id": "yaml-proj",
        "service_account": {"client_email": "a@b.c", "private_key": "key"},
        "report_state": True,
        "secure_devices_pin": "1234",
        "auto_sync": True,
    }
    mock_store.async_set_synced_entities = AsyncMock()

    runtime = GoogleAssistantRuntimeManager(hass, mock_store)
    initial_entities = {"light.office": {"expose": True, "name": "Office Light"}}
    await runtime.async_initialize(initial_entities)

    assert runtime.mode == "yaml_attached"
    assert mock_google_config._config["entity_config"] == initial_entities

    # Mutate in-memory config with auto_sync enabled
    updated_entities = {
        "light.office": {"expose": True, "name": "Office Main Light"},
        "switch.fan": {"expose": True, "name": "Office Fan"},
    }
    await runtime.async_refresh_memory_config(updated_entities, schedule_auto_sync=True)
    assert mock_google_config._config["entity_config"] == updated_entities
    mock_google_config.async_schedule_google_sync_all.assert_called_once()

    # Trigger immediate sync to Google
    result = await runtime.async_sync_to_google(updated_entities)
    assert result["success"] is True
    assert result["status_code"] == 200
    assert result["exposed_count"] == 2
    mock_google_config.async_sync_entities_all.assert_awaited_once()
    mock_store.async_set_synced_entities.assert_awaited_once_with(updated_entities)


@pytest.mark.asyncio
async def test_runtime_bootstraps_standalone_storage_mode():
    """Verify runtime initializes GoogleConfig and GoogleAssistantView directly from .storage when no YAML entry is loaded."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_entries.return_value = []
    hass.services.has_service.return_value = False

    mock_store = MagicMock()
    mock_store.google_settings = {
        "project_id": "storage-proj-1",
        "service_account": {"client_email": "sa@proj.iam.gserviceaccount.com", "private_key": "pem"},
        "report_state": True,
        "secure_devices_pin": "9999",
        "auto_sync": False,
    }
    mock_store.async_set_synced_entities = AsyncMock()

    with patch(
        "custom_components.google_assistant_entity_console.runtime.GoogleConfig"
    ) as mock_gc_cls, patch(
        "custom_components.google_assistant_entity_console.runtime.GoogleAssistantView"
    ) as mock_view_cls:
        mock_gc_instance = MagicMock()
        mock_gc_instance._config = {}
        mock_gc_instance.async_initialize = AsyncMock()
        mock_gc_instance.should_report_state = True
        mock_gc_instance.is_reporting_state = False
        mock_gc_instance.async_get_agent_users.return_value = {}
        mock_gc_cls.return_value = mock_gc_instance

        runtime = GoogleAssistantRuntimeManager(hass, mock_store)
        await runtime.async_initialize({"light.kitchen": {"expose": True, "name": "Kitchen"}})

        assert runtime.mode == "storage"
        mock_gc_instance.async_initialize.assert_awaited_once()
        hass.http.register_view.assert_called_once_with(mock_view_cls.return_value)
        mock_gc_instance.async_enable_report_state.assert_called_once()
```

- [ ] **Step 2: Run `pytest tests/test_runtime.py -v` to verify it fails**

Run: `pytest tests/test_runtime.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.google_assistant_entity_console.runtime'`

- [ ] **Step 3: Implement `custom_components/google_assistant_entity_console/runtime.py`**

Create `custom_components/google_assistant_entity_console/runtime.py`:
```python
"""Zero-reboot runtime manager bridging .storage with HA Core's GoogleConfig."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.google_assistant.const import (
    CONF_ENTITY_CONFIG,
    CONF_EXPOSE_BY_DEFAULT,
    CONF_EXPOSED_DOMAINS,
    CONF_PROJECT_ID,
    CONF_REPORT_STATE,
    CONF_SECURE_DEVICES_PIN,
    CONF_SERVICE_ACCOUNT,
    DATA_CONFIG,
    DEFAULT_EXPOSED_DOMAINS,
    DOMAIN as GA_DOMAIN,
    SERVICE_REQUEST_SYNC,
)
from homeassistant.components.google_assistant.http import (
    GoogleAssistantView,
    GoogleConfig,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DATA_RUNTIME, DOMAIN
from .store import ConsoleStore, async_get_store

_LOGGER = logging.getLogger(__name__)
_VIEW_REGISTERED_KEY = f"{DOMAIN}_ga_view_registered"


def _has_valid_service_account(sa: Any) -> bool:
    return bool(
        isinstance(sa, dict)
        and sa.get("client_email")
        and sa.get("private_key")
    )


class GoogleAssistantRuntimeManager:
    """Manage live GoogleConfig state and HomeGraph syncing without HA restarts."""

    def __init__(self, hass: HomeAssistant, store: ConsoleStore) -> None:
        self.hass = hass
        self.store = store
        self.google_config: GoogleConfig | None = None
        self.mode: str = "unconfigured"
        self._view: GoogleAssistantView | None = None

    def _build_full_config_dict(
        self, entity_config: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        gs = self.store.google_settings
        cfg: dict[str, Any] = {
            CONF_PROJECT_ID: gs.get("project_id", ""),
            CONF_EXPOSE_BY_DEFAULT: False,
            CONF_EXPOSED_DOMAINS: list(DEFAULT_EXPOSED_DOMAINS),
            CONF_ENTITY_CONFIG: dict(entity_config),
            CONF_REPORT_STATE: bool(gs.get("report_state", True)),
        }
        if gs.get("secure_devices_pin"):
            cfg[CONF_SECURE_DEVICES_PIN] = str(gs["secure_devices_pin"])
        if _has_valid_service_account(gs.get("service_account")):
            cfg[CONF_SERVICE_ACCOUNT] = dict(gs["service_account"])
        return cfg

    async def async_initialize(
        self, entity_config: dict[str, dict[str, Any]]
    ) -> None:
        """Attach to existing YAML GoogleConfig or bootstrap standalone .storage GoogleConfig."""
        ga_entries = self.hass.config_entries.async_entries(GA_DOMAIN)
        for entry in ga_entries:
            if (
                entry.state == ConfigEntryState.LOADED
                and getattr(entry, "runtime_data", None) is not None
            ):
                self.google_config = entry.runtime_data
                self.mode = "yaml_attached"
                await self.async_refresh_memory_config(entity_config)
                _LOGGER.info(
                    "Attached to active google_assistant config entry in memory (%d exposed entities)",
                    len(entity_config),
                )
                return

        # Clean up any broken/unloaded SOURCE_IMPORT entries left over after removing YAML
        for entry in list(ga_entries):
            if entry.source == SOURCE_IMPORT and entry.state != ConfigEntryState.LOADED:
                try:
                    await self.hass.config_entries.async_remove(entry.entry_id)
                except Exception as err:
                    _LOGGER.debug("Could not remove stale google_assistant import entry: %s", err)

        project_id = self.store.google_settings.get("project_id", "").strip()
        if not project_id:
            self.mode = "unconfigured"
            return

        config = self._build_full_config_dict(entity_config)
        self.hass.data[DATA_CONFIG] = config

        if self.google_config is None:
            self.google_config = GoogleConfig(self.hass, config)
            await self.google_config.async_initialize()
        else:
            self.google_config._config = config

        # Register /api/google_assistant HTTP endpoint once
        existing_view = self.hass.data.get(_VIEW_REGISTERED_KEY)
        if existing_view is None:
            view = GoogleAssistantView(self.google_config)
            self.hass.http.register_view(view)
            self.hass.data[_VIEW_REGISTERED_KEY] = view
            self._view = view
        else:
            existing_view.config = self.google_config
            self._view = existing_view

        if (
            self.google_config.should_report_state
            and _has_valid_service_account(config.get(CONF_SERVICE_ACCOUNT))
            and not self.google_config.is_reporting_state
        ):
            self.google_config.async_enable_report_state()

        if not self.hass.services.has_service(GA_DOMAIN, SERVICE_REQUEST_SYNC):
            async def _handle_request_sync(call: ServiceCall) -> None:
                if self.google_config is None:
                    return
                agent_user_id = call.data.get("agent_user_id") or call.context.user_id
                if agent_user_id:
                    await self.google_config.async_sync_entities(agent_user_id)
                else:
                    await self.google_config.async_sync_entities_all()

            self.hass.services.async_register(
                GA_DOMAIN, SERVICE_REQUEST_SYNC, _handle_request_sync
            )

        self.mode = "storage"
        _LOGGER.info(
            "Initialized standalone .storage GoogleConfig for project '%s' (%d exposed entities)",
            project_id,
            len(entity_config),
        )

    async def async_switch_to_storage_mode(
        self, entity_config: dict[str, dict[str, Any]]
    ) -> None:
        """Detach from legacy SOURCE_IMPORT entry if present and switch to standalone .storage mode."""
        ga_entries = self.hass.config_entries.async_entries(GA_DOMAIN)
        for entry in list(ga_entries):
            if entry.source == SOURCE_IMPORT:
                if getattr(entry, "runtime_data", None) is not None:
                    self.google_config = entry.runtime_data
                try:
                    await self.hass.config_entries.async_remove(entry.entry_id)
                except Exception as err:
                    _LOGGER.debug("Note while removing legacy import entry: %s", err)
        self.mode = "storage"
        await self.async_refresh_memory_config(entity_config)

    async def async_refresh_memory_config(
        self,
        entity_config: dict[str, dict[str, Any]],
        schedule_auto_sync: bool = False,
    ) -> None:
        """Mutate GoogleConfig._config in memory so changes take effect immediately."""
        if self.google_config is None:
            if self.store.google_settings.get("project_id"):
                await self.async_initialize(entity_config)
            return

        cfg = self.google_config._config
        cfg[CONF_ENTITY_CONFIG] = dict(entity_config)

        gs = self.store.google_settings
        if gs.get("project_id"):
            cfg[CONF_PROJECT_ID] = gs["project_id"]
        if gs.get("secure_devices_pin"):
            cfg[CONF_SECURE_DEVICES_PIN] = str(gs["secure_devices_pin"])
        elif CONF_SECURE_DEVICES_PIN in cfg and not gs.get("secure_devices_pin"):
            cfg.pop(CONF_SECURE_DEVICES_PIN, None)

        if _has_valid_service_account(gs.get("service_account")):
            if cfg.get(CONF_SERVICE_ACCOUNT) != gs["service_account"]:
                cfg[CONF_SERVICE_ACCOUNT] = dict(gs["service_account"])
                self.google_config._access_token = None

        cfg[CONF_REPORT_STATE] = bool(gs.get("report_state", True))
        if (
            cfg[CONF_REPORT_STATE]
            and _has_valid_service_account(cfg.get(CONF_SERVICE_ACCOUNT))
        ):
            if not self.google_config.is_reporting_state:
                self.google_config.async_enable_report_state()
        else:
            if self.google_config.is_reporting_state:
                self.google_config.async_disable_report_state()

        if (
            schedule_auto_sync
            and gs.get("auto_sync", False)
            and _has_valid_service_account(cfg.get(CONF_SERVICE_ACCOUNT))
            and self.google_config.async_get_agent_users()
        ):
            self.google_config.async_schedule_google_sync_all()

    async def async_sync_to_google(
        self, entity_config: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Update in-memory GoogleConfig and trigger live HomeGraph Request Sync."""
        await self.async_refresh_memory_config(entity_config, schedule_auto_sync=False)

        if self.google_config is None:
            await self.store.async_set_synced_entities(entity_config)
            return {
                "success": True,
                "status_code": 204,
                "exposed_count": len(entity_config),
                "agent_users_count": 0,
                "mode": self.mode,
                "synced_offline": True,
                "message": "Saved in .storage. Configure Google Project ID & Service Account in Settings to enable cloud sync.",
            }

        agent_users = list(self.google_config.async_get_agent_users())
        has_sa = _has_valid_service_account(
            self.google_config._config.get(CONF_SERVICE_ACCOUNT)
        )

        if not agent_users or not has_sa:
            await self.store.async_set_synced_entities(entity_config)
            return {
                "success": True,
                "status_code": 204,
                "exposed_count": len(entity_config),
                "agent_users_count": len(agent_users),
                "mode": self.mode,
                "synced_offline": True,
                "message": (
                    "Updated live in memory & .storage. Say 'Hey Google, sync my devices' "
                    "to link/sync with Google Home."
                ),
            }

        status_code = await self.google_config.async_sync_entities_all()
        success = status_code in (200, 204)
        if success:
            await self.store.async_set_synced_entities(entity_config)

        return {
            "success": success,
            "status_code": int(status_code),
            "exposed_count": len(entity_config),
            "agent_users_count": len(agent_users),
            "mode": self.mode,
            "synced_offline": False,
        }

    def get_status_summary(self) -> dict[str, Any]:
        """Return current runtime status for UI display."""
        agent_users = (
            list(self.google_config.async_get_agent_users())
            if self.google_config is not None
            else []
        )
        return {
            "mode": self.mode,
            "project_id": self.store.google_settings.get("project_id", ""),
            "has_service_account": _has_valid_service_account(
                self.store.google_settings.get("service_account")
            ),
            "is_reporting_state": bool(
                self.google_config and self.google_config.is_reporting_state
            ),
            "agent_users_count": len(agent_users),
        }


async def async_get_runtime(
    hass: HomeAssistant,
) -> GoogleAssistantRuntimeManager:
    """Get or create the singleton GoogleAssistantRuntimeManager."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    runtime: GoogleAssistantRuntimeManager | None = domain_data.get(DATA_RUNTIME)
    if runtime is None:
        store = await async_get_store(hass)
        runtime = GoogleAssistantRuntimeManager(hass, store)
        domain_data[DATA_RUNTIME] = runtime
    return runtime
```

- [ ] **Step 4: Run `pytest tests/test_runtime.py -v` to verify it passes**

Run: `pytest tests/test_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add custom_components/google_assistant_entity_console/runtime.py tests/test_runtime.py
git commit -m "feat(runtime): add zero-reboot GoogleAssistantRuntimeManager for live .storage sync"
```

---

### Task 3: Backend API Views & Component Setup (`views.py` & `__init__.py`)

**Files:**
- Modify: `custom_components/google_assistant_entity_console/views.py`
- Modify: `custom_components/google_assistant_entity_console/__init__.py`
- Modify: `tests/test_views.py`
- Modify: `tests/test_blocklist.py`
- Modify: `tests/test_entities.py`

**Interfaces:**
- Consumes: `async_get_store`, `async_get_runtime`
- Produces:
  - `async def async_build_entity_config_map(hass: HomeAssistant) -> dict[str, dict[str, Any]]`
  - `SyncView` (`POST /api/google_assistant_entity_console/sync`) and `RebuildView` (`POST /api/google_assistant_entity_console/rebuild` calling the same live sync logic)
  - `GoogleSettingsView` (`GET/POST /api/google_assistant_entity_console/google_settings`)
  - `MigrateYamlView` (`POST /api/google_assistant_entity_console/migrate_yaml`)
  - Updated `EntitiesView`, `UpdateEntityView`, `BlocklistView`, `BlocklistAddView`, `AISettingsView`

- [ ] **Step 1: Add unit tests for new & updated views in `tests/test_views.py`**

Add tests to `tests/test_views.py` covering:
1. `POST /api/google_assistant_entity_console/sync` (and `/rebuild`) invoking `runtime.async_sync_to_google` and returning `exposed_count`, `status_code`, and `mode`.
2. `GET / POST /api/google_assistant_entity_console/google_settings` reading/updating `project_id`, `service_account`, `report_state`, `secure_devices_pin`, `auto_sync`, and redacting `private_key` on `GET`.
3. `POST /api/google_assistant_entity_console/migrate_yaml` invoking `store.async_migrate_and_disable_yaml()` and `runtime.async_switch_to_storage_mode()`.
4. `POST /api/google_assistant_entity_console/entities/update` refreshing in-memory `GoogleConfig` via `runtime.async_refresh_memory_config(..., schedule_auto_sync=True)`.

```python
@pytest.mark.asyncio
async def test_google_settings_and_live_sync_views(hass_mock):
    from custom_components.google_assistant_entity_console.views import (
        GoogleSettingsView,
        SyncView,
    )
    # Test GET/POST on GoogleSettingsView and POST on SyncView
```

- [ ] **Step 2: Run `pytest tests/test_views.py -v` to verify the new tests fail**

Run: `pytest tests/test_views.py -v`
Expected: FAIL with `ImportError: cannot import name 'GoogleSettingsView'`

- [ ] **Step 3: Update `views.py` and `__init__.py` to wire `ConsoleStore` and `GoogleAssistantRuntimeManager`**

Key updates in `custom_components/google_assistant_entity_console/views.py`:
1. `async_load_blocklist(hass)` / `async_save_blocklist(hass, blocklist)` delegate to `await async_get_store(hass)` (falling back to file helpers only if `hass.data` is not a dict in minimal unit mocks).
2. `async_load_ai_settings(hass)` / `async_save_ai_settings(hass, settings)` delegate to `await async_get_store(hass)`.
3. In `async_fetch_entities_data(hass)`:
   - Compare each entity against `store.synced_entities` (checking membership and whether `display_name`, `aliases`, or `area` changed since last sync) to compute `yaml_exposed` (keeping the field name `yaml_exposed` alongside `synced` for 100% frontend compatibility).
4. Add `async_build_entity_config_map(hass)`:
   ```python
   async def async_build_entity_config_map(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
       entities = await async_fetch_entities_data(hass)
       entity_config: dict[str, dict[str, Any]] = {}
       for ent in entities:
           if not ent["should_expose"]:
               continue
           cfg: dict[str, Any] = {
               "expose": True,
               "name": ent["display_name"],
           }
           if ent["aliases"]:
               cfg["aliases"] = list(ent["aliases"])
           if ent["area"] and ent["area"] != "TBA":
               cfg["room"] = ent["area"]
           entity_config[ent["entity_id"]] = cfg
       return entity_config
   ```
5. Update `UpdateEntityView.post`:
   - After updating `ent_reg`, call:
     ```python
     runtime = await async_get_runtime(hass)
     entity_config = await async_build_entity_config_map(hass)
     await runtime.async_refresh_memory_config(entity_config, schedule_auto_sync=True)
     ```
6. Implement `SyncView` (`/api/google_assistant_entity_console/sync`) and update `RebuildView` (`/api/google_assistant_entity_console/rebuild`) to call `runtime.async_sync_to_google(entity_config)`.
7. Implement `GoogleSettingsView` (`/api/google_assistant_entity_console/google_settings`) and `MigrateYamlView` (`/api/google_assistant_entity_console/migrate_yaml`).
8. In `custom_components/google_assistant_entity_console/__init__.py`:
   - Initialize `store = await async_get_store(hass)` and `runtime = await async_get_runtime(hass)` in `async_setup_entry`, call `await runtime.async_initialize(await async_build_entity_config_map(hass))`, and register `SyncView()`, `GoogleSettingsView()`, and `MigrateYamlView()`.

- [ ] **Step 4: Run all backend unit tests**

Run: `pytest tests/test_store.py tests/test_runtime.py tests/test_views.py tests/test_blocklist.py tests/test_entities.py tests/test_config_flow.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 3**

```bash
git add custom_components/google_assistant_entity_console/views.py custom_components/google_assistant_entity_console/__init__.py tests/test_views.py tests/test_blocklist.py tests/test_entities.py
git commit -m "feat(views): wire .storage store, live sync endpoint, and Google credentials API"
```

---

### Task 4: Frontend UI — Live Sync Button & Google Assistant `.storage` Settings (`static/`)

**Files:**
- Modify: `custom_components/google_assistant_entity_console/static/index.html`
- Modify: `custom_components/google_assistant_entity_console/static/app.js`
- Modify: `custom_components/google_assistant_entity_console/static/style.css`
- Modify: `tests/test_playwright_e2e.py`

**Interfaces:**
- Consumes:
  - `GET /api/google_assistant_entity_console/entities`
  - `POST /api/google_assistant_entity_console/sync`
  - `GET / POST /api/google_assistant_entity_console/google_settings`
  - `POST /api/google_assistant_entity_console/migrate_yaml`
- Produces:
  - Header **Sync to Google** button (`#rebuildBtn`) that syncs live and refreshes entity badges without opening `#restartModal`.
  - **Google Assistant Connection (`.storage`)** section in `#aiSettingsModal` with inputs:
    - `#gaProjectIdInput`
    - `#gaServiceAccountInput` & `#gaServiceAccountStatus`
    - `#gaPinInput`
    - `#gaReportStateToggle`
    - `#gaAutoSyncToggle`
    - `#migrateYamlBtn` (visible when `has_legacy_yaml` is true)

- [ ] **Step 1: Add Playwright E2E tests in `tests/test_playwright_e2e.py`**

Add E2E test cases verifying:
1. Clicking **Sync to Google** calls `/api/google_assistant_entity_console/sync` (or `/rebuild`), clears pending badges immediately, shows a success toast, and does **not** open `#restartModal`.
2. Opening the Settings modal loads Google Assistant `.storage` settings (`project_id`, `client_email` status badge, `report_state`, `auto_sync`), saves updated settings via `POST /api/google_assistant_entity_console/google_settings`, and triggers one-click YAML migration via `#migrateYamlBtn`.

- [ ] **Step 2: Run Playwright E2E test to verify it fails**

Run: `pytest tests/test_playwright_e2e.py -v`
Expected: FAIL (new Google Connection settings inputs and live sync behavior not yet in `index.html` / `app.js`)

- [ ] **Step 3: Update `index.html`, `app.js`, and `style.css`**

1. In `custom_components/google_assistant_entity_console/static/index.html`:
   - Update `#rebuildBtn` text/icon from `Rebuild YAML` to `<i class="fa-solid fa-cloud-arrow-up"></i> Sync to Google`.
   - In `#aiSettingsModal`, add the **Google Assistant Connection (`.storage`)** panel above the AI Assistant configuration with `#gaProjectIdInput`, `#gaPinInput`, `#gaServiceAccountInput`, `#gaServiceAccountStatus`, `#gaReportStateToggle`, `#gaAutoSyncToggle`, and `#migrateYamlBtn`.
2. In `custom_components/google_assistant_entity_console/static/app.js`:
   - Update header status display (`#configFile`) to show `.storage Live (<project_id>)` or `YAML Attached (<project_id>)`.
   - Update `handleRebuild()` to call `/api/google_assistant_entity_console/sync`, refresh entities (`await fetchEntities()`), and show a live toast (`Synced ${result.exposed_count} entities to Google HomeGraph!`) without opening `restartModal`.
   - Update `loadAiSettings()` and the Settings save handler to also load and save `/api/google_assistant_entity_console/google_settings` and wire `#migrateYamlBtn` to `POST /api/google_assistant_entity_console/migrate_yaml`.

- [ ] **Step 4: Run full test suite (`pytest`)**

Run: `pytest -v`
Expected: PASS (all unit and Playwright E2E tests pass)

- [ ] **Step 5: Commit Task 4**

```bash
git add custom_components/google_assistant_entity_console/static/index.html custom_components/google_assistant_entity_console/static/app.js custom_components/google_assistant_entity_console/static/style.css tests/test_playwright_e2e.py
git commit -m "feat(ui): replace YAML rebuild/restart flow with live .storage Sync to Google and credentials UI"
```
