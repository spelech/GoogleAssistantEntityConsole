from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.google_assistant_entity_console.runtime import (
    GoogleAssistantRuntimeManager,
    async_get_runtime,
)


@pytest.mark.asyncio
async def test_runtime_attaches_to_existing_yaml_google_config():
    """Verify runtime attaches to an active google_assistant ConfigEntry and mutates _config in place."""
    hass = MagicMock()
    hass.data = {}
    mock_google_config = MagicMock()
    mock_google_config._config = {"project_id": "yaml-proj", "entity_config": {}}
    mock_google_config.is_reporting_state = True
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
    await runtime.async_refresh_memory_config(
        updated_entities, schedule_auto_sync=True
    )
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
        "service_account": {
            "client_email": "sa@proj.iam.gserviceaccount.com",
            "private_key": "pem",
        },
        "report_state": True,
        "secure_devices_pin": "9999",
        "auto_sync": False,
    }
    mock_store.async_set_synced_entities = AsyncMock()

    with (
        patch(
            "custom_components.google_assistant_entity_console.runtime.GoogleConfig"
        ) as mock_gc_cls,
        patch(
            "custom_components.google_assistant_entity_console.runtime.GoogleAssistantView"
        ) as mock_view_cls,
    ):
        mock_gc_instance = MagicMock()
        mock_gc_instance._config = {}
        mock_gc_instance.async_initialize = AsyncMock()
        mock_gc_instance.should_report_state = True
        mock_gc_instance.is_reporting_state = False
        mock_gc_instance.async_get_agent_users.return_value = {}
        mock_gc_cls.return_value = mock_gc_instance

        runtime = GoogleAssistantRuntimeManager(hass, mock_store)
        await runtime.async_initialize(
            {"light.kitchen": {"expose": True, "name": "Kitchen"}}
        )

        assert runtime.mode == "storage"
        mock_gc_instance.async_initialize.assert_awaited_once()
        hass.http.register_view.assert_called_once_with(mock_view_cls.return_value)
        mock_gc_instance.async_enable_report_state.assert_called_once()

        # Verify offline sync when no agent_users linked yet still saves synced_entities
        sync_res = await runtime.async_sync_to_google(
            {"light.kitchen": {"expose": True, "name": "Kitchen"}}
        )
        assert sync_res["success"] is True
        assert sync_res["synced_offline"] is True
        mock_store.async_set_synced_entities.assert_awaited_once()
