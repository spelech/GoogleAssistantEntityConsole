import json
from unittest.mock import MagicMock

import pytest

from custom_components.google_assistant_entity_console.store import (
    ConsoleStore,
    async_get_store,
)


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
    hass.data = {}
    hass.config.path.side_effect = lambda *parts: str(tmp_path.joinpath(*parts))

    async def async_add_executor_job(func, *args):
        return func(*args)

    hass.async_add_executor_job = async_add_executor_job

    store = await async_get_store(hass)

    assert store.blocklist == [r"^sensor\.ignored_.*"]
    assert store.ai_settings["ha_agent_id"] == "conversation.gemini"
    assert store.google_settings["project_id"] == "my-home-project-123"
    assert store.google_settings["secure_devices_pin"] == "4321"
    assert store.google_settings["report_state"] is True
    assert (
        store.google_settings["service_account"]["client_email"]
        == "homegraph@my-home-project-123.iam.gserviceaccount.com"
    )
    assert "light.kitchen" in store.synced_entities
    assert store.synced_entities["light.kitchen"]["name"] == "Kitchen Light"
    assert await store.async_has_legacy_yaml() is True

    # Test commenting out google_assistant in configuration.yaml
    mig_res = await store.async_migrate_and_disable_yaml()
    assert mig_res["commented_out"] is True
    assert await store.async_has_legacy_yaml() is False
    updated_conf = (tmp_path / "configuration.yaml").read_text(encoding="utf-8")
    assert "# google_assistant: !include gaGen_101726.yaml" in updated_conf


@pytest.mark.asyncio
async def test_store_update_google_settings_and_validation(tmp_path):
    """Test updating Google settings via ConsoleStore and validating service account JSON."""
    hass = MagicMock()
    hass.data = {}
    hass.config.path.side_effect = lambda *parts: str(tmp_path.joinpath(*parts))

    async def async_add_executor_job(func, *args):
        return func(*args)

    hass.async_add_executor_job = async_add_executor_job

    store = ConsoleStore(hass)
    await store.async_load()

    await store.async_update_google_settings(
        {
            "project_id": "new-proj-999",
            "report_state": False,
            "secure_devices_pin": "8888",
            "auto_sync": True,
            "service_account": json.dumps(
                {
                    "client_email": "test@new-proj-999.iam.gserviceaccount.com",
                    "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
                }
            ),
        }
    )

    assert store.google_settings["project_id"] == "new-proj-999"
    assert store.google_settings["report_state"] is False
    assert store.google_settings["secure_devices_pin"] == "8888"
    assert store.google_settings["auto_sync"] is True
    assert (
        store.google_settings["service_account"]["client_email"]
        == "test@new-proj-999.iam.gserviceaccount.com"
    )

    with pytest.raises(ValueError, match="client_email"):
        await store.async_update_google_settings(
            {"service_account": {"invalid": "dict"}}
        )
