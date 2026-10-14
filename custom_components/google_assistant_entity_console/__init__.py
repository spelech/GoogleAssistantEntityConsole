import logging

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .views import (
    AIGenerateNicknamesView,
    AIGenerateSingleEntityNicknameView,
    AIHaAgentsView,
    AIModelsView,
    AISettingsView,
    AISuggestExposureView,
    BlocklistAddView,
    BlocklistView,
    EntitiesView,
    RebuildView,
    RestartView,
    UpdateEntityView,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Google Assistant Entity Console component (legacy YAML fallback)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Google Assistant Entity Console from a config entry."""
    _LOGGER.info("Setting up Google Assistant Entity Console from config entry")

    # Read version natively via Home Assistant loader for cache busting
    from homeassistant.loader import async_get_integration
    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = integration.version
    except Exception as err:
        _LOGGER.error("Failed to read version from integration loader: %s", err)
        version = "1.0.3"

    # 1. Register static files directory
    static_dir = hass.config.path("custom_components/google_assistant_entity_console/static")
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            "/google_assistant_entity_console/static",
            static_dir,
            True,
        )
    ])

    # 2. Register API views
    hass.http.register_view(EntitiesView())
    hass.http.register_view(UpdateEntityView())
    hass.http.register_view(RebuildView())
    hass.http.register_view(RestartView())
    hass.http.register_view(BlocklistView())
    hass.http.register_view(BlocklistAddView())
    hass.http.register_view(AISettingsView())
    hass.http.register_view(AIModelsView())
    hass.http.register_view(AIHaAgentsView())
    hass.http.register_view(AIGenerateNicknamesView())
    hass.http.register_view(AISuggestExposureView())
    hass.http.register_view(AIGenerateSingleEntityNicknameView())

    # 3. Register Sidebar Panel
    async_remove_panel(hass, DOMAIN, warn_if_unknown=False)

    async_register_built_in_panel(
        hass=hass,
        component_name="custom",
        sidebar_title="Google Sync",
        sidebar_icon="mdi:google-assistant",
        frontend_url_path=DOMAIN,
        require_admin=False,
        config={
            "_panel_custom": {
                "name": "google-assistant-entity-console-panel",
                "js_url": f"/google_assistant_entity_console/static/panel.js?v={version}",
            },
            "version": version,
        },
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Google Assistant Entity Console config entry")
    async_remove_panel(hass, DOMAIN, warn_if_unknown=False)
    return True
