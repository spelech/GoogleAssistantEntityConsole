"""Comprehensive tests for API view endpoints and AI response parsing.

Covers:
- load_ai_settings & save_ai_settings persistence and error handling
- AISettingsView: GET and POST (validation, persistence, error handling)
- AIModelsView: POST (validation, querying upstream, sorting, response shapes, HTTP errors)
- AIHaAgentsView: GET (listing HA agents, empty list, error handling)
- UpdateEntityView: POST (entity name, aliases sanitization, should_expose, 400/404/500 errors)
- AIGenerateNicknamesView: POST (validation, trimming/cleaning, individual LLM failure resiliency)
- AISuggestExposureView: POST (validation, raw JSON vs markdown codeblocks, malformed JSON handling)
- AIGenerateSingleEntityNicknameView: POST (validation, room context formatting, nickname cleaning)
- async_call_llm: Home Assistant and OpenAI sources (validation, error speech, empty speech, HTTP errors)
- EntitiesView & RestartView: GET and POST lifecycle behaviors
- ComputedNameType singleton fallback handling
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.google_assistant_entity_console.views import (
    AIGenerateNicknamesView,
    AIGenerateSingleEntityNicknameView,
    AIHaAgentsView,
    AIModelsView,
    AISettingsView,
    AISuggestExposureView,
    EntitiesView,
    RestartView,
    UpdateEntityView,
    async_call_llm,
    async_fetch_entities_data,
    load_ai_settings,
    save_ai_settings,
)


# ===========================================================================
# 1. Storage & Persistence Helpers: load_ai_settings and save_ai_settings
# ===========================================================================

def test_load_ai_settings_file_not_found(mock_hass, tmp_path):
    """Returns empty dict {} when settings file does not exist."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    assert not (tmp_path / "google_assistant_entity_console_ai_settings.json").exists()
    assert load_ai_settings(mock_hass) == {}


def test_save_and_load_ai_settings_roundtrip(mock_hass, tmp_path):
    """Persists settings formatted with indent 2 and accurately reloads them."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    sample_settings = {
        "ai_source": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-testkey123",
        "model": "gpt-4o",
    }

    save_ai_settings(mock_hass, sample_settings)

    file_path = tmp_path / "google_assistant_entity_console_ai_settings.json"
    assert file_path.exists()

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data == sample_settings

    loaded = load_ai_settings(mock_hass)
    assert loaded == sample_settings


def test_load_ai_settings_corrupted_json(mock_hass, tmp_path):
    """Handles corrupted JSON file gracefully by returning empty dict {}."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    file_path = tmp_path / "google_assistant_entity_console_ai_settings.json"
    file_path.write_text("{broken: json[val", encoding="utf-8")

    assert load_ai_settings(mock_hass) == {}


@pytest.mark.parametrize(
    "invalid_content",
    [
        '["item1", "item2"]',  # list
        '"plain_string"',      # string
        "12345",               # integer
        "true",                # boolean
        "null",                # null
    ],
)
def test_load_ai_settings_non_dict_json(mock_hass, tmp_path, invalid_content):
    """Handles valid JSON that is not a dictionary gracefully by returning {}."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    file_path = tmp_path / "google_assistant_entity_console_ai_settings.json"
    file_path.write_text(invalid_content, encoding="utf-8")

    assert load_ai_settings(mock_hass) == {}


def test_save_ai_settings_io_error_handled(mock_hass):
    """Handles write errors gracefully by logging without raising uncaught exceptions."""
    with patch("builtins.open", side_effect=OSError("Disk full")):
        save_ai_settings(mock_hass, {"model": "test"})


# ===========================================================================
# 2. AISettingsView: GET and POST
# ===========================================================================

@pytest.mark.anyio
async def test_ai_settings_view_get_success(mock_hass):
    """Returns stored settings in the 'settings' dictionary with 200 status."""
    view = AISettingsView()
    request = MagicMock()
    request.app = {"hass": mock_hass}

    sample_settings = {"base_url": "https://api.openai.com/v1", "model": "gpt-4"}
    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value=sample_settings):
        resp = await view.get(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["settings"] == sample_settings


@pytest.mark.anyio
async def test_ai_settings_view_get_error(mock_hass):
    """Returns 500 error response if reading settings raises an unexpected exception."""
    view = AISettingsView()
    request = MagicMock()
    request.app = {"hass": mock_hass}

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", side_effect=RuntimeError("Storage failure")):
        resp = await view.get(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data["error"] == "Storage failure"


@pytest.mark.anyio
async def test_ai_settings_view_post_success(mock_hass):
    """Validates dictionary settings, saves them, and returns 200."""
    view = AISettingsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    payload = {
        "settings": {
            "ai_source": "openai",
            "base_url": "https://api.openrouter.ai/v1",
            "api_key": "test_key",
            "model": "anthropic/claude-3-opus",
        }
    }
    request.json.return_value = payload

    with patch("custom_components.google_assistant_entity_console.views.save_ai_settings") as mock_save:
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["success"] is True
        assert data["settings"] == payload["settings"]
        mock_save.assert_called_once_with(mock_hass, payload["settings"])


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_settings",
    [
        "not_a_dictionary",
        [1, 2, 3],
        12345,
        True,
    ],
)
async def test_ai_settings_view_post_invalid_payload(mock_hass, invalid_settings):
    """Rejects non-dictionary settings payload with HTTP 400."""
    view = AISettingsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"settings": invalid_settings}

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert data["error"] == "Settings must be a dictionary"


@pytest.mark.anyio
async def test_ai_settings_view_post_save_error(mock_hass):
    """Returns 500 if an error occurs while saving settings."""
    view = AISettingsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"settings": {"model": "test"}}

    with patch("custom_components.google_assistant_entity_console.views.save_ai_settings", side_effect=Exception("Write failed")):
        resp = await view.post(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data["error"] == "Write failed"


# ===========================================================================
# 3. AIModelsView: POST
# ===========================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"base_url": ""},
        {"api_key": "some_key"},
    ],
)
async def test_ai_models_view_post_missing_base_url(mock_hass, payload):
    """Returns 400 when base_url is missing or empty."""
    view = AIModelsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = payload

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert data["error"] == "Missing base URL"


@pytest.mark.anyio
async def test_ai_models_view_post_success_dict_data_and_sorting(mock_hass):
    """Queries upstream /models, parses OpenAI dict structure, and sorts models alphabetically by name."""
    view = AIModelsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "base_url": "https://api.openrouter.ai/v1/",
        "api_key": "secret_token",
    }

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "openai/gpt-4", "name": "GPT-4", "pricing": {"prompt": "0.00003"}},
            {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku", "pricing": {"prompt": "0.00000025"}},
            {"id": "meta/llama-3-8b", "pricing": {"prompt": "0.0"}},  # missing name -> falls back to id
        ]
    }

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    with patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())

        # Verify endpoint called with stripped trailing slash and Authorization header
        mock_session.get.assert_called_once_with(
            "https://api.openrouter.ai/v1/models",
            headers={"Authorization": "Bearer secret_token"},
            timeout=10,
        )

        models = data["models"]
        assert len(models) == 3
        # Sorted by lowercased name: "Claude 3 Haiku", "GPT-4", "meta/llama-3-8b"
        assert models[0]["name"] == "Claude 3 Haiku"
        assert models[0]["id"] == "anthropic/claude-3-haiku"
        assert models[1]["name"] == "GPT-4"
        assert models[2]["name"] == "meta/llama-3-8b"  # fallback to id


@pytest.mark.anyio
async def test_ai_models_view_post_success_raw_list_and_no_api_key(mock_hass):
    """Parses raw list model response and verifies headers when api_key is empty."""
    view = AIModelsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "base_url": "http://localhost:11434/v1",
        "api_key": "",
    }

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = [
        {"id": "mistral:latest", "name": "Mistral 7B"},
        {"id": "codellama:latest", "name": "CodeLlama 7B"},
    ]

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    with patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())

        # No Authorization header when api_key is empty
        mock_session.get.assert_called_once_with(
            "http://localhost:11434/v1/models",
            headers={},
            timeout=10,
        )

        models = data["models"]
        assert len(models) == 2
        assert models[0]["name"] == "CodeLlama 7B"
        assert models[1]["name"] == "Mistral 7B"


@pytest.mark.anyio
async def test_ai_models_view_post_skips_malformed_items(mock_hass):
    """Skips non-dictionary items or items without an 'id' property."""
    view = AIModelsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"base_url": "https://api.openai.com/v1"}

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "gpt-4o", "name": "GPT-4o"},
            {"name": "No ID"},          # missing 'id' -> skipped
            "string_instead_of_dict",    # not a dict -> skipped
            42,                          # not a dict -> skipped
            None,                        # None -> skipped
        ]
    }

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    with patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert len(data["models"]) == 1
        assert data["models"][0]["id"] == "gpt-4o"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("upstream_status", "upstream_text"),
    [
        (401, "Unauthorized: Invalid API key"),
        (403, "Forbidden: Access denied"),
        (404, "Models endpoint not found"),
        (500, "Internal Server Error"),
    ],
)
async def test_ai_models_view_post_upstream_http_error(mock_hass, upstream_status, upstream_text):
    """Forwards upstream HTTP errors with matching status code and explanatory error message."""
    view = AIModelsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "base_url": "https://api.openai.com/v1",
        "api_key": "bad_key",
    }

    mock_resp = AsyncMock()
    mock_resp.status = upstream_status
    mock_resp.text.return_value = upstream_text

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    with patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        resp = await view.post(request)
        assert resp.status == upstream_status
        data = json.loads(resp.body.decode())
        assert data["error"] == f"Failed to fetch models (HTTP {upstream_status}): {upstream_text}"


@pytest.mark.anyio
async def test_ai_models_view_post_network_exception(mock_hass):
    """Returns 500 when network connection or HTTP request raises an exception."""
    view = AIModelsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"base_url": "https://api.openai.com/v1"}

    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("Connection refused")

    with patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        resp = await view.post(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data["error"] == "Connection refused"


# ===========================================================================
# 4. AIHaAgentsView: GET
# ===========================================================================

@pytest.mark.anyio
async def test_ai_ha_agents_view_get_success(mock_hass):
    """Lists registered Home Assistant conversation agents."""
    view = AIHaAgentsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}

    agent1 = MagicMock()
    agent1.id = "conversation.openai"
    agent1.name = "OpenAI Agent"

    agent2 = MagicMock()
    agent2.id = "conversation.home_assistant"
    agent2.name = "Home Assistant"

    with patch("custom_components.google_assistant_entity_console.views.async_get_agent_info", return_value=[agent1, agent2]):
        resp = await view.get(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["agents"] == [
            {"id": "conversation.openai", "name": "OpenAI Agent"},
            {"id": "conversation.home_assistant", "name": "Home Assistant"},
        ]


@pytest.mark.anyio
async def test_ai_ha_agents_view_get_empty(mock_hass):
    """Returns empty agents list when no conversation agents are registered."""
    view = AIHaAgentsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}

    with patch("custom_components.google_assistant_entity_console.views.async_get_agent_info", return_value=[]):
        resp = await view.get(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["agents"] == []


@pytest.mark.anyio
async def test_ai_ha_agents_view_get_error(mock_hass):
    """Returns 500 when fetching agent info raises an exception."""
    view = AIHaAgentsView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}

    with patch("custom_components.google_assistant_entity_console.views.async_get_agent_info", side_effect=Exception("Registry error")):
        resp = await view.get(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data["error"] == "Registry error"


# ===========================================================================
# 5. UpdateEntityView: POST
# ===========================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "New Name"},
        {"entity_id": ""},
        {"entity_id": None},
    ],
)
async def test_update_entity_view_missing_entity_id(mock_hass, payload):
    """Returns 400 when entity_id is missing or empty."""
    view = UpdateEntityView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = payload

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert data["error"] == "Missing entity_id"


@pytest.mark.anyio
async def test_update_entity_view_nonexistent_entity(mock_hass, mock_entity_registry):
    """Returns 404 when the target entity is not registered in entity_registry."""
    view = UpdateEntityView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"entity_id": "light.ghost_light"}

    with patch("custom_components.google_assistant_entity_console.views.entity_registry.async_get", return_value=mock_entity_registry):
        resp = await view.post(request)
        assert resp.status == 404
        data = json.loads(resp.body.decode())
        assert data["error"] == "Entity light.ghost_light not found"


@pytest.mark.anyio
async def test_update_entity_view_updates_name_and_sanitizes_aliases(mock_hass, mock_entity_registry):
    """Updates entity name, sanitizes aliases by removing zeros, empty strings, and None, and sets exposure."""
    view = UpdateEntityView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}

    mock_entry = MagicMock(entity_id="light.kitchen")
    mock_entity_registry.entities["light.kitchen"] = mock_entry

    request.json.return_value = {
        "entity_id": "light.kitchen",
        "name": "Kitchen Ceiling Light",
        "aliases": ["kitchen spot", "0", 0, "", None, False, "prep light", "island light"],
        "should_expose": True,
    }

    with patch("custom_components.google_assistant_entity_console.views.entity_registry.async_get", return_value=mock_entity_registry):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["success"] is True

        # Check async_update_entity called with sanitized alias set
        mock_entity_registry.async_update_entity.assert_called_once_with(
            "light.kitchen",
            name="Kitchen Ceiling Light",
            aliases={"kitchen spot", "prep light", "island light"},
        )

        # Check async_update_entity_options called with conversation should_expose: True
        mock_entity_registry.async_update_entity_options.assert_called_once_with(
            "light.kitchen",
            "conversation",
            {"should_expose": True},
        )


@pytest.mark.anyio
async def test_update_entity_view_empty_name_resets_to_none(mock_hass, mock_entity_registry):
    """Resets name to None when an empty string is provided."""
    view = UpdateEntityView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}

    mock_entry = MagicMock(entity_id="light.kitchen")
    mock_entity_registry.entities["light.kitchen"] = mock_entry
    request.json.return_value = {
        "entity_id": "light.kitchen",
        "name": "",
    }

    with patch("custom_components.google_assistant_entity_console.views.entity_registry.async_get", return_value=mock_entity_registry):
        resp = await view.post(request)
        assert resp.status == 200
        mock_entity_registry.async_update_entity.assert_called_once_with(
            "light.kitchen",
            name=None,
            aliases=None,
        )


@pytest.mark.anyio
async def test_update_entity_view_empty_aliases_clears_aliases(mock_hass, mock_entity_registry):
    """Clears aliases by passing an empty set when empty list [] is provided."""
    view = UpdateEntityView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}

    mock_entry = MagicMock(entity_id="light.kitchen")
    mock_entity_registry.entities["light.kitchen"] = mock_entry
    request.json.return_value = {
        "entity_id": "light.kitchen",
        "aliases": [],
    }

    with patch("custom_components.google_assistant_entity_console.views.entity_registry.async_get", return_value=mock_entity_registry):
        resp = await view.post(request)
        assert resp.status == 200
        mock_entity_registry.async_update_entity.assert_called_once_with(
            "light.kitchen",
            name=None,
            aliases=set(),
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("should_expose_input", "expected_bool"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (None, False),
        ("", False),
    ],
)
async def test_update_entity_view_should_expose_boolean_conversion(mock_hass, mock_entity_registry, should_expose_input, expected_bool):
    """Converts should_expose value to boolean strictly."""
    view = UpdateEntityView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}

    mock_entry = MagicMock(entity_id="light.kitchen")
    mock_entity_registry.entities["light.kitchen"] = mock_entry
    request.json.return_value = {
        "entity_id": "light.kitchen",
        "should_expose": should_expose_input,
    }

    with patch("custom_components.google_assistant_entity_console.views.entity_registry.async_get", return_value=mock_entity_registry):
        resp = await view.post(request)
        assert resp.status == 200
        mock_entity_registry.async_update_entity_options.assert_called_once_with(
            "light.kitchen",
            "conversation",
            {"should_expose": expected_bool},
        )


@pytest.mark.anyio
async def test_update_entity_view_exception_returns_500(mock_hass, mock_entity_registry):
    """Returns 500 when registry update raises an unexpected exception."""
    view = UpdateEntityView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}

    mock_entry = MagicMock(entity_id="light.kitchen")
    mock_entity_registry.entities["light.kitchen"] = mock_entry
    mock_entity_registry.async_update_entity.side_effect = Exception("Registry lock timeout")
    request.json.return_value = {"entity_id": "light.kitchen", "name": "New Light"}

    with patch("custom_components.google_assistant_entity_console.views.entity_registry.async_get", return_value=mock_entity_registry):
        resp = await view.post(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data["error"] == "Registry lock timeout"


# ===========================================================================
# 6. AIGenerateNicknamesView: POST
# ===========================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"entities": []},
    ],
)
async def test_ai_generate_nicknames_missing_entities(mock_hass, payload):
    """Returns 400 when entities list is missing or empty."""
    view = AIGenerateNicknamesView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = payload

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert data["error"] == "No entities provided"


@pytest.mark.anyio
async def test_ai_generate_nicknames_success_cleaning_and_formatting(mock_hass):
    """Calls LLM for multiple entities and cleans whitespace, quotes, and trailing commas from nicknames."""
    view = AIGenerateNicknamesView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entities": [
            {"entity_id": "light.living_room", "display_name": "Living Room Light"},
            {"entity_id": "switch.coffee_maker", "name": "Coffee Maker"},
        ]
    }

    async def mock_llm_call(hass, prompt, settings):
        if "Living Room Light" in prompt:
            # LLM returns quotes, trailing comma, and extra spaces
            return ' "main light" , \'couch lamp\', reading light, '
        elif "Coffee Maker" in prompt:
            return "espresso machine, morning brew, coffee pot"
        return ""

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={}), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", side_effect=mock_llm_call):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())

        results = data["results"]
        assert results["light.living_room"] == ["main light", "couch lamp", "reading light"]
        assert results["switch.coffee_maker"] == ["espresso machine", "morning brew", "coffee pot"]


@pytest.mark.anyio
async def test_ai_generate_nicknames_fallback_friendly_name_and_custom_prompt(mock_hass):
    """Uses custom nickname prompt template and falls back to entity id suffix if names are missing."""
    view = AIGenerateNicknamesView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entities": [
            {"entity_id": "light.kitchen_strip_light"},  # No display_name or name
        ]
    }

    captured_prompts = []

    async def mock_llm(hass, prompt, settings):
        captured_prompts.append(prompt)
        return "counter light, strip light"

    custom_settings = {
        "nickname_prompt": "Custom prompt for {friendly_name} with ID {entity_id}",
    }

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value=custom_settings), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", side_effect=mock_llm):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["results"]["light.kitchen_strip_light"] == ["counter light", "strip light"]
        assert len(captured_prompts) == 1
        # Fallback friendly_name is entity_id suffix "kitchen_strip_light"
        assert captured_prompts[0] == "Custom prompt for kitchen_strip_light with ID light.kitchen_strip_light"


@pytest.mark.anyio
async def test_ai_generate_nicknames_individual_failure_resilience(mock_hass):
    """Gracefully handles individual entity LLM failures without failing the entire batch."""
    view = AIGenerateNicknamesView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entities": [
            {"entity_id": "light.good_light", "display_name": "Good Light"},
            {"entity_id": "light.failing_light", "display_name": "Failing Light"},
        ]
    }

    async def mock_llm_call(hass, prompt, settings):
        if "Good Light" in prompt:
            return "desk lamp, reading light"
        raise RuntimeError("LLM rate limit reached")

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={}), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", side_effect=mock_llm_call):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        # Successfully processed entity is returned
        assert "light.good_light" in data["results"]
        assert data["results"]["light.good_light"] == ["desk lamp", "reading light"]
        # Failing entity is omitted from results without crashing
        assert "light.failing_light" not in data["results"]


@pytest.mark.anyio
async def test_ai_generate_nicknames_general_exception_returns_500(mock_hass):
    """Returns 500 when an unhandled exception occurs in request processing."""
    view = AIGenerateNicknamesView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.side_effect = Exception("JSON parse failure")

    resp = await view.post(request)
    assert resp.status == 500
    data = json.loads(resp.body.decode())
    assert data["error"] == "JSON parse failure"


# ===========================================================================
# 7. AISuggestExposureView: POST
# ===========================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"entities": []},
        {"entities": [], "user_intent": "expose all lights"},
    ],
)
async def test_ai_suggest_exposure_missing_entities(mock_hass, payload):
    """Returns 400 when entities are missing or empty."""
    view = AISuggestExposureView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = payload

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert data["error"] == "No entities provided"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"entities": [{"entity_id": "light.kitchen"}]},
        {"entities": [{"entity_id": "light.kitchen"}], "user_intent": ""},
        {"entities": [{"entity_id": "light.kitchen"}], "user_intent": None},
    ],
)
async def test_ai_suggest_exposure_missing_intent(mock_hass, payload):
    """Returns 400 when user intent is missing or empty."""
    view = AISuggestExposureView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = payload

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert data["error"] == "No user intent/criteria provided"


@pytest.mark.anyio
async def test_ai_suggest_exposure_success_raw_json(mock_hass):
    """Parses raw JSON array returned by the LLM."""
    view = AISuggestExposureView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entities": [
            {"entity_id": "light.kitchen", "display_name": "Kitchen", "domain": "light"},
            {"entity_id": "switch.heater", "display_name": "Heater", "domain": "switch"},
        ],
        "user_intent": "only expose lights",
    }

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={}), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", return_value='["light.kitchen"]'):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["exposed_ids"] == ["light.kitchen"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "markdown_content",
    [
        '```json\n["light.kitchen", "light.bedroom"]\n```',
        '```JSON\n["light.kitchen", "light.bedroom"]\n```',
        '```\n["light.kitchen", "light.bedroom"]\n```',
        '```json\n["light.kitchen", "light.bedroom"]```',
    ],
)
async def test_ai_suggest_exposure_success_markdown_codeblock(mock_hass, markdown_content):
    """Strips markdown codeblock fences (```json ... ```) and parses the enclosed JSON array."""
    view = AISuggestExposureView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entities": [{"entity_id": "light.kitchen"}, {"entity_id": "light.bedroom"}],
        "user_intent": "all lights",
    }

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={}), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", return_value=markdown_content):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["exposed_ids"] == ["light.kitchen", "light.bedroom"]


@pytest.mark.anyio
async def test_ai_suggest_exposure_custom_prompt(mock_hass):
    """Formats custom exposure_prompt template with user_intent and entities_list."""
    view = AISuggestExposureView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entities": [{"entity_id": "light.kitchen", "display_name": "Kitchen Light", "domain": "light"}],
        "user_intent": "only voice controllable lights",
    }

    captured_prompts = []

    async def mock_llm(hass, prompt, settings):
        captured_prompts.append(prompt)
        return '["light.kitchen"]'

    custom_settings = {
        "exposure_prompt": "CRITERIA: {user_intent}\nENTITIES:\n{entities_list}",
    }

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value=custom_settings), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", side_effect=mock_llm):
        resp = await view.post(request)
        assert resp.status == 200
        assert len(captured_prompts) == 1
        assert "CRITERIA: only voice controllable lights" in captured_prompts[0]
        assert "light.kitchen" in captured_prompts[0]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "malformed_output",
    [
        "Sure, you should expose light.kitchen and switch.heater!",
        "```json\n{not valid json\n```",
        "['single_quotes_invalid_in_json']",
        "",
    ],
)
async def test_ai_suggest_exposure_malformed_llm_json(mock_hass, malformed_output):
    """Returns 502 with error details when LLM returns non-JSON or invalid JSON format."""
    view = AISuggestExposureView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entities": [{"entity_id": "light.kitchen"}],
        "user_intent": "all lights",
    }

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={}), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", return_value=malformed_output):
        resp = await view.post(request)
        assert resp.status == 502
        data = json.loads(resp.body.decode())
        assert "LLM returned invalid format" in data["error"]


@pytest.mark.anyio
async def test_ai_suggest_exposure_upstream_llm_failure(mock_hass):
    """Returns 500 when upstream LLM execution raises an exception."""
    view = AISuggestExposureView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entities": [{"entity_id": "light.kitchen"}],
        "user_intent": "all lights",
    }

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={}), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", side_effect=RuntimeError("Upstream timeout")):
        resp = await view.post(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data["error"] == "Upstream timeout"


# ===========================================================================
# 8. AIGenerateSingleEntityNicknameView: POST
# ===========================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"entity_id": ""},
        {"display_name": "Kitchen Light"},
    ],
)
async def test_ai_generate_single_nickname_missing_entity_id(mock_hass, payload):
    """Returns 400 when entity_id is missing or empty."""
    view = AIGenerateSingleEntityNicknameView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = payload

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert data["error"] == "Missing entity_id"


@pytest.mark.anyio
async def test_ai_generate_single_nickname_room_context_formatting(mock_hass):
    """Excludes target entity from room context and formats other room entities with names and aliases."""
    view = AIGenerateSingleEntityNicknameView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entity_id": "light.desk_lamp",
        "display_name": "Desk Lamp",
        "room_entities": [
            # Target entity: must be excluded from room context string
            {"entity_id": "light.desk_lamp", "display_name": "Desk Lamp"},
            # Peer entity with aliases:
            {"entity_id": "light.ceiling", "display_name": "Ceiling Light", "aliases": ["overhead", "main lamp"]},
            # Peer entity without aliases:
            {"entity_id": "switch.fan", "name": "Exhaust Fan"},
        ],
    }

    captured_prompts = []

    async def mock_llm(hass, prompt, settings):
        captured_prompts.append(prompt)
        return ' "study lamp", \'work light\', reading light , '

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={}), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", side_effect=mock_llm):
        resp = await view.post(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())

        # Nicknames are trimmed and quotes removed
        assert data["aliases"] == ["study lamp", "work light", "reading light"]

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        # Target entity must NOT be listed under other entities in the same room
        assert "Other Entities in same room: light.ceiling (name: Ceiling Light, current nicknames: ['overhead', 'main lamp']); switch.fan (name: Exhaust Fan)" in prompt
        assert "Target Entity ID: light.desk_lamp" in prompt


@pytest.mark.anyio
async def test_ai_generate_single_nickname_empty_room_context(mock_hass):
    """Sets room context to 'None' when no other entities are in the room."""
    view = AIGenerateSingleEntityNicknameView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entity_id": "light.solo_light",
        "display_name": "Solo Light",
        "room_entities": [
            {"entity_id": "light.solo_light", "display_name": "Solo Light"},
        ],
    }

    captured_prompts = []

    async def mock_llm(hass, prompt, settings):
        captured_prompts.append(prompt)
        return "corner light, accent lamp"

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={}), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", side_effect=mock_llm):
        resp = await view.post(request)
        assert resp.status == 200
        assert "Other Entities in same room: None" in captured_prompts[0]


@pytest.mark.anyio
async def test_ai_generate_single_nickname_custom_prompt(mock_hass):
    """Uses custom single_nickname_prompt template from settings."""
    view = AIGenerateSingleEntityNicknameView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entity_id": "light.kitchen",
        "display_name": "Kitchen",
        "room_entities": [],
    }

    captured_prompts = []

    async def mock_llm(hass, prompt, settings):
        captured_prompts.append(prompt)
        return "kitchen light, island"

    custom_settings = {
        "single_nickname_prompt": "GENERATE: {entity_id} - {friendly_name} [ROOM: {room_context}]",
    }

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value=custom_settings), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", side_effect=mock_llm):
        resp = await view.post(request)
        assert resp.status == 200
        assert captured_prompts[0] == "GENERATE: light.kitchen - Kitchen [ROOM: None]"


@pytest.mark.anyio
async def test_ai_generate_single_nickname_llm_failure(mock_hass):
    """Returns 500 when LLM call fails."""
    view = AIGenerateSingleEntityNicknameView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {
        "entity_id": "light.kitchen",
    }

    with patch("custom_components.google_assistant_entity_console.views.load_ai_settings", return_value={}), \
         patch("custom_components.google_assistant_entity_console.views.async_call_llm", side_effect=RuntimeError("AI failure")):
        resp = await view.post(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data["error"] == "AI failure"


# ===========================================================================
# 9. async_call_llm: Home Assistant and OpenAI sources
# ===========================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "ha_settings",
    [
        {"ai_source": "home_assistant"},
        {"ai_source": "home_assistant", "ha_agent_id": ""},
        {"ai_source": "home_assistant", "ha_agent_id": None},
    ],
)
async def test_async_call_llm_ha_missing_agent_id(mock_hass, ha_settings):
    """Raises ValueError when Home Assistant agent is not selected in settings."""
    with pytest.raises(ValueError, match="Home Assistant conversation agent is not selected"):
        await async_call_llm(mock_hass, "Test prompt", ha_settings)


@pytest.mark.anyio
async def test_async_call_llm_ha_error_speech(mock_hass):
    """Raises RuntimeError with error speech when HA conversation agent returns an error response."""
    test_settings = {
        "ai_source": "home_assistant",
        "ha_agent_id": "conversation.openai",
    }

    mock_result = MagicMock()
    mock_result.response.response_type = "error"
    mock_result.response.as_dict.return_value = {
        "speech": {"plain": {"speech": "Failed to contact upstream conversation model"}},
    }

    with patch("custom_components.google_assistant_entity_console.views.async_converse", return_value=mock_result):
        with pytest.raises(RuntimeError, match="HA Conversation Agent error: Failed to contact upstream conversation model"):
            await async_call_llm(mock_hass, "Test prompt", test_settings)


@pytest.mark.anyio
async def test_async_call_llm_ha_error_speech_unknown(mock_hass):
    """Raises RuntimeError with 'Unknown error' when HA agent returns error with no speech payload."""
    test_settings = {
        "ai_source": "home_assistant",
        "ha_agent_id": "conversation.openai",
    }

    mock_result = MagicMock()
    mock_result.response.response_type = "error"
    mock_result.response.as_dict.return_value = {}

    with patch("custom_components.google_assistant_entity_console.views.async_converse", return_value=mock_result):
        with pytest.raises(RuntimeError, match="HA Conversation Agent error: Unknown error"):
            await async_call_llm(mock_hass, "Test prompt", test_settings)


@pytest.mark.anyio
async def test_async_call_llm_ha_empty_speech(mock_hass):
    """Raises RuntimeError when HA conversation agent succeeds but returns empty speech string."""
    test_settings = {
        "ai_source": "home_assistant",
        "ha_agent_id": "conversation.openai",
    }

    mock_result = MagicMock()
    mock_result.response.response_type = "action_done"
    mock_result.response.as_dict.return_value = {
        "speech": {"plain": {"speech": ""}},
    }

    with patch("custom_components.google_assistant_entity_console.views.async_converse", return_value=mock_result):
        with pytest.raises(RuntimeError, match="HA Conversation Agent returned an empty response"):
            await async_call_llm(mock_hass, "Test prompt", test_settings)


@pytest.mark.anyio
async def test_async_call_llm_ha_success(mock_hass):
    """Returns trimmed speech string on successful Home Assistant agent conversation."""
    test_settings = {
        "ai_source": "home_assistant",
        "ha_agent_id": "conversation.openai",
    }

    mock_result = MagicMock()
    mock_result.response.response_type = "action_done"
    mock_result.response.as_dict.return_value = {
        "speech": {"plain": {"speech": "  kitchen main, cooking light  "}},
    }

    with patch("custom_components.google_assistant_entity_console.views.async_converse", return_value=mock_result) as mock_converse:
        res = await async_call_llm(mock_hass, "Suggest nicknames", test_settings)
        assert res == "kitchen main, cooking light"
        mock_converse.assert_called_once()
        call_kwargs = mock_converse.call_args[1]
        assert call_kwargs["text"] == "Suggest nicknames"
        assert call_kwargs["agent_id"] == "conversation.openai"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "openai_settings",
    [
        {"ai_source": "openai"},
        {"ai_source": "openai", "base_url": "https://api.openai.com/v1"},  # missing model
        {"ai_source": "openai", "model": "gpt-4"},                          # missing base_url
        {"base_url": "", "model": "gpt-4"},                                # empty base_url
    ],
)
async def test_async_call_llm_openai_missing_config(mock_hass, openai_settings):
    """Raises ValueError when base URL or Model is missing for OpenAI compatible source."""
    with pytest.raises(ValueError, match="AI settings are incomplete. Please configure base URL and Model in Settings."):
        await async_call_llm(mock_hass, "Test prompt", openai_settings)


@pytest.mark.anyio
async def test_async_call_llm_openai_success(mock_hass):
    """Sends payload with temperature, max_tokens, prompt, and Authorization header to /chat/completions."""
    test_settings = {
        "ai_source": "openai",
        "base_url": "https://api.openai.com/v1/",
        "api_key": "sk-testsecretkey",
        "model": "gpt-4o",
    }

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "choices": [
            {"message": {"content": "  table lamp, night light  "}}
        ]
    }

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_resp

    with patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        res = await async_call_llm(mock_hass, "Generate nicknames", test_settings)
        assert res == "table lamp, night light"

        # Verify POST URL stripped trailing slash
        mock_session.post.assert_called_once()
        args, kwargs = mock_session.post.call_args
        assert args[0] == "https://api.openai.com/v1/chat/completions"
        assert kwargs["headers"] == {
            "Content-Type": "application/json",
            "Authorization": "Bearer sk-testsecretkey",
        }
        assert kwargs["json"] == {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Generate nicknames"}],
            "temperature": 0.1,
            "max_tokens": 1000,
        }
        assert kwargs["timeout"] == 25


@pytest.mark.anyio
async def test_async_call_llm_openai_no_api_key(mock_hass):
    """Omits Authorization header when api_key is empty."""
    test_settings = {
        "ai_source": "openai",
        "base_url": "http://localhost:11434/v1",
        "api_key": "",
        "model": "llama3:latest",
    }

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "desk light"}}]
    }

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_resp

    with patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        res = await async_call_llm(mock_hass, "Nicknames", test_settings)
        assert res == "desk light"

        _, kwargs = mock_session.post.call_args
        assert kwargs["headers"] == {"Content-Type": "application/json"}
        assert "Authorization" not in kwargs["headers"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("err_status", "err_body"),
    [
        (401, "Incorrect API key provided"),
        (429, "Rate limit reached for requests"),
        (500, "Upstream model server crashed"),
    ],
)
async def test_async_call_llm_openai_http_error(mock_hass, err_status, err_body):
    """Raises RuntimeError with HTTP status and body when OpenAI endpoint returns non-200."""
    test_settings = {
        "ai_source": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "bad_key",
        "model": "gpt-4",
    }

    mock_resp = AsyncMock()
    mock_resp.status = err_status
    mock_resp.text.return_value = err_body

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_resp

    with patch("custom_components.google_assistant_entity_console.views.async_get_clientsession", return_value=mock_session):
        with pytest.raises(RuntimeError, match=f"API Error \\({err_status}\\): {err_body}"):
            await async_call_llm(mock_hass, "Prompt", test_settings)


# ===========================================================================
# 10. EntitiesView, RestartView, and ComputedName Handling
# ===========================================================================

@pytest.mark.anyio
async def test_entities_view_get_success(mock_hass):
    """Returns serialized entities, current yaml filename, and integration version."""
    view = EntitiesView()
    request = MagicMock()
    request.app = {"hass": mock_hass}

    sample_entities = [
        {"entity_id": "light.kitchen", "display_name": "Kitchen", "domain": "light"}
    ]

    mock_integration = MagicMock()
    mock_integration.version = "1.0.3"

    with patch("custom_components.google_assistant_entity_console.views.async_fetch_entities_data", return_value=sample_entities), \
         patch("custom_components.google_assistant_entity_console.views.get_current_yaml_filename", return_value="gaGen_090726.yaml"), \
         patch("homeassistant.loader.async_get_integration", AsyncMock(return_value=mock_integration)):
        resp = await view.get(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["entities"] == sample_entities
        assert data["yaml_filename"] == "gaGen_090726.yaml"
        assert data["version"] == "1.0.3"


@pytest.mark.anyio
async def test_entities_view_get_version_fallback_on_exception(mock_hass):
    """Falls back to version 'Unknown' when async_get_integration raises an exception."""
    view = EntitiesView()
    request = MagicMock()
    request.app = {"hass": mock_hass}

    with patch("custom_components.google_assistant_entity_console.views.async_fetch_entities_data", return_value=[]), \
         patch("custom_components.google_assistant_entity_console.views.get_current_yaml_filename", return_value=None), \
         patch("homeassistant.loader.async_get_integration", side_effect=Exception("Integration not found")):
        resp = await view.get(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data["version"] == "Unknown"
        assert data["yaml_filename"] == "None"


@pytest.mark.anyio
async def test_entities_view_get_error(mock_hass):
    """Returns 500 when fetching entities raises an exception."""
    view = EntitiesView()
    request = MagicMock()
    request.app = {"hass": mock_hass}

    with patch("custom_components.google_assistant_entity_console.views.async_fetch_entities_data", side_effect=Exception("Registry corrupted")):
        resp = await view.get(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data["error"] == "Registry corrupted"


@pytest.mark.anyio
async def test_restart_view_post_success(mock_hass):
    """Calls homeassistant restart service non-blocking and returns success."""
    view = RestartView()
    request = MagicMock()
    request.app = {"hass": mock_hass}

    resp = await view.post(request)
    assert resp.status == 200
    data = json.loads(resp.body.decode())
    assert data["success"] is True
    mock_hass.services.async_call.assert_called_once_with("homeassistant", "restart", blocking=False)


@pytest.mark.anyio
async def test_restart_view_post_error(mock_hass):
    """Returns 500 when restart service call raises an exception."""
    view = RestartView()
    request = MagicMock()
    request.app = {"hass": mock_hass}
    mock_hass.services.async_call.side_effect = Exception("Service unavailable")

    resp = await view.post(request)
    assert resp.status == 500
    data = json.loads(resp.body.decode())
    assert data["error"] == "Service unavailable"


@pytest.mark.anyio
async def test_computed_name_handling(mock_hass):
    """Verifies that Home Assistant ComputedNameType singleton instances are filtered from aliases and handled for names."""
    class MockComputedNameType:
        def __str__(self):
            return "<ComputedNameType._singleton: 0>"

    dummy_computed_name = MockComputedNameType()

    mock_ent_reg = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entity_id = "light.kitchen"
    mock_entry.disabled_by = None
    mock_entry.hidden_by = None
    mock_entry.device_id = "dev_123"
    mock_entry.device_class = None
    mock_entry.original_device_class = None
    mock_entry.area_id = None

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

