import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from custom_components.google_assistant_entity_console.views import (
    load_ai_settings,
    save_ai_settings,
    AISettingsView,
    AIModelsView,
    AIGenerateNicknamesView,
    AISuggestExposureView,
    AIGenerateSingleEntityNicknameView,
)


def test_load_save_ai_settings(mock_hass):
    # Test setting loading on non-existing path
    with patch("os.path.exists", return_value=False):
        settings = load_ai_settings(mock_hass)
        assert settings == {}

    # Test saving settings
    test_settings = {"base_url": "https://api.openai.com/v1", "model": "gpt-4"}
    with patch("builtins.open", MagicMock()) as mock_open:
        save_ai_settings(mock_hass, test_settings)
        mock_open.assert_called_once_with("dummy_settings.json", "w", encoding="utf-8")


@pytest.mark.anyio
async def test_ai_settings_view_get(mock_hass):
    view = AISettingsView()
    request = MagicMock()
    request.app = {"hass": mock_hass}
    
    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={"base_url": "test"}):
        resp = await view.get(request)
        data = json.loads(resp.body.decode())
        assert data["settings"]["base_url"] == "test"


@pytest.mark.anyio
async def test_ai_models_view_post(mock_hass):
    view = AIModelsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "base_url": "https://api.openrouter.ai/v1",
        "api_key": "test_key"
    }

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "id": "openai/gpt-4",
                "name": "GPT-4",
                "pricing": {"prompt": "0.00001", "completion": "0.00003"}
            }
        ]
    }

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    with patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        resp = await view.post(request)
        data = json.loads(resp.body.decode())
        assert "models" in data
        assert len(data["models"]) == 1
        assert data["models"][0]["id"] == "openai/gpt-4"
        assert data["models"][0]["pricing"]["prompt"] == "0.00001"


@pytest.mark.anyio
async def test_ai_generate_single_nickname(mock_hass):
    view = AIGenerateSingleEntityNicknameView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entity_id": "light.kitchen_light",
        "display_name": "Kitchen Light",
        "room_entities": [
            {"entity_id": "light.kitchen_pendant", "display_name": "Kitchen Pendant", "aliases": ["pendant"]}
        ]
    }

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "choices": [
            {"message": {"content": "cooking light, kitchen main"}}
        ]
    }

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_resp

    test_settings = {
        "base_url": "https://api.openrouter.ai/v1",
        "api_key": "test_key",
        "model": "openai/gpt-4"
    }

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value=test_settings), \
         patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        resp = await view.post(request)
        data = json.loads(resp.body.decode())
        assert "aliases" in data
        assert "cooking light" in data["aliases"]
        assert "kitchen main" in data["aliases"]


@pytest.mark.anyio
async def test_ai_ha_agents_view(mock_hass):
    from custom_components.google_assistant_entity_console.views import AIHaAgentsView
    view = AIHaAgentsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    
    mock_agent = MagicMock()
    mock_agent.id = "conversation.openai"
    mock_agent.name = "OpenAI Agent"
    
    with patch("custom_components.google_assistant_entity_console.views.async_get_agent_info", return_value=[mock_agent]):
        resp = await view.get(request)
        data = json.loads(resp.body.decode())
        assert "agents" in data
        assert len(data["agents"]) == 1
        assert data["agents"][0]["id"] == "conversation.openai"
        assert data["agents"][0]["name"] == "OpenAI Agent"


@pytest.mark.anyio
async def test_async_call_llm_home_assistant(mock_hass):
    from custom_components.google_assistant_entity_console.views import async_call_llm
    
    test_settings = {
        "ai_source": "home_assistant",
        "ha_agent_id": "conversation.openai"
    }
    
    mock_result = MagicMock()
    mock_result.response.response_type = "action_done"
    mock_result.response.as_dict.return_value = {
        "speech": {"plain": {"speech": "cooking light, kitchen main"}}
    }
    
    with patch("custom_components.google_assistant_entity_console.views.async_converse", return_value=mock_result) as mock_converse:
        response_text = await async_call_llm(mock_hass, "Test prompt", test_settings)
        assert response_text == "cooking light, kitchen main"
        mock_converse.assert_called_once()


@pytest.mark.anyio
async def test_computed_name_handling(mock_hass):
    from custom_components.google_assistant_entity_console.views import async_fetch_entities_data
    
    # Mock some dummy enum or class instance that resembles ComputedNameType._singleton
    class MockComputedNameType:
        def __str__(self):
            return "<ComputedNameType._singleton: 0>"
    
    dummy_computed_name = MockComputedNameType()
    
    # Setup mock registries
    mock_ent_reg = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entity_id = "light.kitchen"
    mock_entry.disabled_by = None
    mock_entry.hidden_by = None
    mock_entry.device_id = "dev_123"
    mock_entry.device_class = None
    mock_entry.original_device_class = None
    mock_entry.area_id = None
    
    # Set COMPUTED_NAME singleton value on name and original_name and raw aliases
    mock_entry.name = dummy_computed_name
    mock_entry.original_name = dummy_computed_name
    mock_entry.aliases = [dummy_computed_name, "kitchen_alias"]
    mock_entry.options = {}
    mock_entry.platform = "hue"
    
    mock_ent_reg.entities = {"light.kitchen": mock_entry}
    
    mock_dev_reg = MagicMock()
    mock_dev = MagicMock()
    mock_dev.id = "dev_123"
    mock_dev.area_id = None
    mock_dev.name_by_user = dummy_computed_name
    mock_dev.name = dummy_computed_name
    mock_dev_reg.devices = {"dev_123": mock_dev}
    
    with patch("custom_components.google_assistant_entity_console.views.entity_registry.async_get", return_value=mock_ent_reg), \
         patch("custom_components.google_assistant_entity_console.views.device_registry.async_get", return_value=mock_dev_reg), \
         patch("custom_components.google_assistant_entity_console.views.area_registry.async_get", return_value=MagicMock()), \
         patch("custom_components.google_assistant_entity_console.views.floor_registry.async_get", return_value=MagicMock()), \
         patch("custom_components.google_assistant_entity_console.views.get_current_yaml_filename", return_value="dummy.yaml"), \
         patch("custom_components.google_assistant_entity_console.views.load_yaml_exposed_entities", return_value={}):
        
        entities = await async_fetch_entities_data(mock_hass)
        assert len(entities) == 1
        ent = entities[0]
        # Should fallback to formatting the entity ID name part
        assert ent["display_name"] == "Kitchen"
        # The COMPUTED_NAME alias should be filtered out, leaving only the string alias
        assert ent["aliases"] == ["kitchen_alias"]
