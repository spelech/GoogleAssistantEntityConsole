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
        ga_entries = (
            self.hass.config_entries.async_entries(GA_DOMAIN)
            if hasattr(self.hass, "config_entries")
            and hasattr(self.hass.config_entries, "async_entries")
            else []
        )
        if not isinstance(ga_entries, list):
            ga_entries = []

        for entry in ga_entries:
            if (
                getattr(entry, "state", None) == ConfigEntryState.LOADED
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
            if (
                getattr(entry, "source", None) == SOURCE_IMPORT
                and getattr(entry, "state", None) != ConfigEntryState.LOADED
            ):
                try:
                    await self.hass.config_entries.async_remove(entry.entry_id)
                except Exception as err:
                    _LOGGER.debug(
                        "Could not remove stale google_assistant import entry: %s", err
                    )

        project_id = self.store.google_settings.get("project_id", "").strip()
        if not project_id:
            self.mode = "unconfigured"
            return

        config = self._build_full_config_dict(entity_config)
        if not isinstance(getattr(self.hass, "data", None), dict):
            self.hass.data = {}
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

        if hasattr(self.hass, "services") and not self.hass.services.has_service(
            GA_DOMAIN, SERVICE_REQUEST_SYNC
        ):
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
        ga_entries = (
            self.hass.config_entries.async_entries(GA_DOMAIN)
            if hasattr(self.hass, "config_entries")
            and hasattr(self.hass.config_entries, "async_entries")
            else []
        )
        if isinstance(ga_entries, list):
            for entry in list(ga_entries):
                if getattr(entry, "source", None) == SOURCE_IMPORT:
                    if getattr(entry, "runtime_data", None) is not None:
                        self.google_config = entry.runtime_data
                    try:
                        await self.hass.config_entries.async_remove(entry.entry_id)
                    except Exception as err:
                        _LOGGER.debug(
                            "Note while removing legacy import entry: %s", err
                        )
        if self.google_config is None and self.store.google_settings.get("project_id"):
            await self.async_initialize(entity_config)
        else:
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
        if cfg[CONF_REPORT_STATE] and _has_valid_service_account(
            cfg.get(CONF_SERVICE_ACCOUNT)
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
    if not isinstance(getattr(hass, "data", None), dict):
        hass.data = {}
    domain_data = hass.data.setdefault(DOMAIN, {})
    runtime: GoogleAssistantRuntimeManager | None = domain_data.get(DATA_RUNTIME)
    if runtime is None:
        store = await async_get_store(hass)
        runtime = GoogleAssistantRuntimeManager(hass, store)
        domain_data[DATA_RUNTIME] = runtime
    return runtime
