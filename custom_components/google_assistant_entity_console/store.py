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
            if isinstance(full_loaded, dict) and isinstance(
                full_loaded.get("google_assistant"), dict
            ):
                ga_data = full_loaded["google_assistant"]
        except Exception:
            ga_data = None

    if not isinstance(ga_data, dict):
        return {}

    google_settings: dict[str, Any] = {}
    project_id = ga_data.get("project_id")
    if project_id and not str(project_id).startswith("!secret "):
        google_settings["project_id"] = str(project_id)
    if "report_state" in ga_data:
        google_settings["report_state"] = bool(ga_data.get("report_state"))
    pin = ga_data.get("secure_devices_pin")
    if pin and not str(pin).startswith("!secret "):
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
        if (
            not stored["google_settings"].get("project_id")
            or not stored["synced_entities"]
        ):
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
                raise ValueError(
                    "Service account JSON must contain 'client_email' and 'private_key'."
                )
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
    if not isinstance(getattr(hass, "data", None), dict):
        hass.data = {}
    domain_data = hass.data.setdefault(DOMAIN, {})
    store: ConsoleStore | None = domain_data.get(DATA_STORE)
    if store is None:
        store = ConsoleStore(hass)
        await store.async_load()
        domain_data[DATA_STORE] = store
    return store
