"""Tests for Google Assistant Entity Console config flow and lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.google_assistant_entity_console import (
    async_remove_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.google_assistant_entity_console.config_flow import ConfigFlow
from custom_components.google_assistant_entity_console.const import DOMAIN
from custom_components.google_assistant_entity_console.views import (
    AIGenerateNicknamesView,
    AIGenerateSingleEntityNicknameView,
    AIHaAgentsView,
    AIModelsView,
    AISettingsView,
    AISuggestExposureView,
    BlocklistAddView,
    BlocklistView,
    EntitiesView,
    GoogleSettingsView,
    McpStreamableView,
    MigrateYamlView,
    RebuildView,
    RestartView,
    SyncView,
    UpdateEntityView,
)


@pytest.fixture
def lifecycle_hass(mock_hass):
    """Setup mock_hass with http attributes and paths needed for lifecycle tests."""
    mock_hass.http = MagicMock()
    mock_hass.http.async_register_static_paths = AsyncMock()
    mock_hass.http.register_view = MagicMock()
    mock_hass.config.path = MagicMock(side_effect=lambda p: f"/config/{p}")
    return mock_hass


# ---------------------------------------------------------------------------
# Config Flow Tests
# ---------------------------------------------------------------------------


def test_config_flow_version():
    """Verify that ConfigFlow version is 1."""
    assert ConfigFlow.VERSION == 1


@pytest.mark.anyio
async def test_config_flow_user_step_initial_form():
    """Test user step shows form with step_id 'user' when no input is provided."""
    flow = ConfigFlow()
    flow._async_current_entries = MagicMock(return_value=[])

    result = await flow.async_step_user()
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result.get("errors") is None


@pytest.mark.anyio
async def test_config_flow_user_step_creates_entry_empty_input():
    """Test user step creates entry with title 'Google Sync' and empty data."""
    flow = ConfigFlow()
    flow._async_current_entries = MagicMock(return_value=[])

    result = await flow.async_step_user(user_input={})
    assert result["type"] == "create_entry"
    assert result["title"] == "Google Sync"
    assert result["data"] == {}


@pytest.mark.anyio
async def test_config_flow_user_step_creates_entry_with_extra_input():
    """Test user step creates entry with title 'Google Sync' and empty data even if extra input is passed."""
    flow = ConfigFlow()
    flow._async_current_entries = MagicMock(return_value=[])

    result = await flow.async_step_user(user_input={"extra_param": "ignored"})
    assert result["type"] == "create_entry"
    assert result["title"] == "Google Sync"
    assert result["data"] == {}


@pytest.mark.anyio
async def test_config_flow_user_step_single_instance_abort_no_input():
    """Test user step aborts with reason 'single_instance_allowed' when an entry exists."""
    flow = ConfigFlow()
    existing_entry = MagicMock()
    flow._async_current_entries = MagicMock(return_value=[existing_entry])

    result = await flow.async_step_user()
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.anyio
async def test_config_flow_user_step_single_instance_abort_with_input():
    """Test user step aborts with reason 'single_instance_allowed' when an entry exists even if input is passed."""
    flow = ConfigFlow()
    existing_entry = MagicMock()
    flow._async_current_entries = MagicMock(return_value=[existing_entry])

    result = await flow.async_step_user(user_input={"some": "value"})
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


# ---------------------------------------------------------------------------
# Integration Setup Lifecycle Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_async_setup_legacy(lifecycle_hass):
    """Test async_setup returns True for legacy YAML configuration."""
    result = await async_setup(lifecycle_hass, {})
    assert result is True


@pytest.mark.anyio
async def test_async_setup_entry_success(lifecycle_hass):
    """Test async_setup_entry registers static paths, all 12 views, and sidebar panel."""
    mock_entry = MagicMock()
    expected_version = "2.4.1"

    with patch(
        "homeassistant.loader.async_get_integration", new_callable=AsyncMock
    ) as mock_get_integration, patch(
        "custom_components.google_assistant_entity_console.async_remove_panel"
    ) as mock_remove_panel, patch(
        "custom_components.google_assistant_entity_console.async_register_built_in_panel"
    ) as mock_register_panel:
        mock_integration = MagicMock()
        mock_integration.version = expected_version
        mock_get_integration.return_value = mock_integration

        result = await async_setup_entry(lifecycle_hass, mock_entry)
        assert result is True

        # 1. Verify static path registration
        lifecycle_hass.http.async_register_static_paths.assert_awaited_once()
        static_paths = lifecycle_hass.http.async_register_static_paths.call_args[0][0]
        assert len(static_paths) == 1
        static_path_config = static_paths[0]
        assert static_path_config.url_path == "/google_assistant_entity_console/static"
        assert (
            static_path_config.path
            == "/config/custom_components/google_assistant_entity_console/static"
        )
        assert static_path_config.cache_headers is True

        # 2. Verify registration of all 16 API views in exact order
        assert lifecycle_hass.http.register_view.call_count == 16
        registered_classes = [
            call.args[0].__class__
            for call in lifecycle_hass.http.register_view.call_args_list
        ]
        expected_classes = [
            EntitiesView,
            UpdateEntityView,
            SyncView,
            RebuildView,
            RestartView,
            GoogleSettingsView,
            MigrateYamlView,
            BlocklistView,
            BlocklistAddView,
            AISettingsView,
            AIModelsView,
            AIHaAgentsView,
            AIGenerateNicknamesView,
            AISuggestExposureView,
            AIGenerateSingleEntityNicknameView,
            McpStreamableView,
        ]
        assert registered_classes == expected_classes

        # 3. Verify panel removal and re-registration
        mock_remove_panel.assert_called_once_with(
            lifecycle_hass, DOMAIN, warn_if_unknown=False
        )
        mock_register_panel.assert_called_once()
        panel_kwargs = mock_register_panel.call_args.kwargs
        assert panel_kwargs["hass"] == lifecycle_hass
        assert panel_kwargs["component_name"] == "custom"
        assert panel_kwargs["sidebar_title"] == "Google Sync"
        assert panel_kwargs["sidebar_icon"] == "mdi:google-assistant"
        assert panel_kwargs["frontend_url_path"] == DOMAIN
        assert panel_kwargs["require_admin"] is False
        assert panel_kwargs["config"] == {
            "_panel_custom": {
                "name": "google-assistant-entity-console-panel",
                "js_url": f"/google_assistant_entity_console/static/panel.js?v={expected_version}",
            },
            "version": expected_version,
        }


@pytest.mark.anyio
async def test_async_setup_entry_version_fallback_on_error(lifecycle_hass):
    """Test async_setup_entry falls back gracefully to version 3.0.0 when loader fails."""
    mock_entry = MagicMock()

    with patch(
        "homeassistant.loader.async_get_integration",
        side_effect=RuntimeError("Integration lookup failed"),
    ), patch(
        "custom_components.google_assistant_entity_console.async_remove_panel"
    ), patch(
        "custom_components.google_assistant_entity_console.async_register_built_in_panel"
    ) as mock_register_panel:
        result = await async_setup_entry(lifecycle_hass, mock_entry)
        assert result is True

        panel_kwargs = mock_register_panel.call_args.kwargs
        assert panel_kwargs["config"]["version"] == "3.0.0"
        assert (
            panel_kwargs["config"]["_panel_custom"]["js_url"]
            == "/google_assistant_entity_console/static/panel.js?v=3.0.0"
        )


@pytest.mark.anyio
async def test_async_setup_entry_panel_lifecycle_order(lifecycle_hass):
    """Test async_setup_entry removes existing panel before registering new panel."""
    mock_entry = MagicMock()
    call_order = []

    def record_remove(*args, **kwargs):
        call_order.append("remove")

    def record_register(*args, **kwargs):
        call_order.append("register")

    with patch(
        "custom_components.google_assistant_entity_console.async_remove_panel",
        side_effect=record_remove,
    ), patch(
        "custom_components.google_assistant_entity_console.async_register_built_in_panel",
        side_effect=record_register,
    ):
        result = await async_setup_entry(lifecycle_hass, mock_entry)
        assert result is True
        assert call_order == ["remove", "register"]


# ---------------------------------------------------------------------------
# Integration Unload Lifecycle Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_async_unload_entry(lifecycle_hass):
    """Test async_unload_entry removes panel and returns True."""
    mock_entry = MagicMock()

    with patch(
        "custom_components.google_assistant_entity_console.async_remove_panel"
    ) as mock_remove_panel:
        result = await async_unload_entry(lifecycle_hass, mock_entry)
        assert result is True
        mock_remove_panel.assert_called_once_with(
            lifecycle_hass, DOMAIN, warn_if_unknown=False
        )


@pytest.mark.anyio
async def test_async_remove_entry(lifecycle_hass):
    """Test async_remove_entry cleanly uninstalls and cleans up hass.data[DOMAIN]."""
    mock_entry = MagicMock()
    lifecycle_hass.data[DOMAIN] = {"some": "runtime_data"}

    with patch(
        "custom_components.google_assistant_entity_console.async_remove_panel"
    ) as mock_remove_panel:
        await async_remove_entry(lifecycle_hass, mock_entry)
        mock_remove_panel.assert_called_once_with(
            lifecycle_hass, DOMAIN, warn_if_unknown=False
        )
        assert DOMAIN not in lifecycle_hass.data
