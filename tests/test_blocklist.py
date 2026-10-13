"""Tests for regex blocklist engine, storage persistence, API views, and entity filtering."""

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.google_assistant_entity_console.views import (
    BlocklistAddView,
    BlocklistView,
    async_fetch_entities_data,
    async_load_blocklist,
    async_save_blocklist,
    load_blocklist,
    save_blocklist,
)

# ===========================================================================
# 1. Storage & Persistence: load_blocklist and save_blocklist
# ===========================================================================

def test_load_blocklist_nonexistent_file(mock_hass, tmp_path):
    """Returns empty list [] when blocklist file does not exist on disk."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    assert not (tmp_path / "google_assistant_entity_console_blocklist.json").exists()
    assert load_blocklist(mock_hass) == []


def test_save_and_load_blocklist_roundtrip(mock_hass, tmp_path):
    """Saves list of patterns as JSON to disk and reloads them accurately."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    patterns = [".*_battery_level$", r"sensor\.weather_.*", r"^media_player\."]

    save_blocklist(mock_hass, patterns)

    file_path = tmp_path / "google_assistant_entity_console_blocklist.json"
    assert file_path.exists()

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data == patterns

    loaded = load_blocklist(mock_hass)
    assert loaded == patterns


@pytest.mark.anyio
async def test_async_save_and_load_blocklist_roundtrip(mock_hass, tmp_path):
    """Saves list of patterns asynchronously and reloads accurately."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    patterns = [r"^switch\.secret_.*", r".*_power$"]

    await async_save_blocklist(mock_hass, patterns)
    loaded = await async_load_blocklist(mock_hass)
    assert loaded == patterns


def test_load_blocklist_corrupted_json(mock_hass, tmp_path):
    """Handles corrupted JSON file gracefully by returning an empty list []."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    file_path = tmp_path / "google_assistant_entity_console_blocklist.json"
    file_path.write_text("{corrupted: [invalid, json...", encoding="utf-8")

    assert load_blocklist(mock_hass) == []


@pytest.mark.parametrize(
    "invalid_content",
    [
        '{"patterns": [".*_battery$"]}',  # Dict instead of list
        '"just_a_string"',                # String
        "12345",                          # Integer
        "true",                           # Boolean
        "null",                           # Null
    ],
)
def test_load_blocklist_non_list_json(mock_hass, tmp_path, invalid_content):
    """Handles valid JSON that is not a list gracefully by returning []."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    file_path = tmp_path / "google_assistant_entity_console_blocklist.json"
    file_path.write_text(invalid_content, encoding="utf-8")

    assert load_blocklist(mock_hass) == []


def test_save_blocklist_io_error_handling(mock_hass):
    """Handles write errors gracefully by logging without raising uncaught exceptions."""
    mock_hass.config.path.side_effect = lambda filename: f"/nonexistent/dir/{filename}"
    with patch("builtins.open", side_effect=OSError("Permission denied")):
        # Should not raise exception
        save_blocklist(mock_hass, ["test_pattern"])


# ===========================================================================
# 2. BlocklistView: GET
# ===========================================================================

@pytest.mark.anyio
async def test_blocklist_view_get_success(mock_hass):
    """Returns JSON {"blocklist": [...]} with current blocklist patterns."""
    view = BlocklistView()
    request = MagicMock()
    request.app = {"hass": mock_hass}

    sample_blocklist = [".*_battery_level$", r"^media_player\."]
    with patch(
        "custom_components.google_assistant_entity_console.views.load_blocklist",
        return_value=sample_blocklist,
    ):
        resp = await view.get(request)
        assert resp.status == 200
        data = json.loads(resp.body.decode())
        assert data == {"blocklist": sample_blocklist}


@pytest.mark.anyio
async def test_blocklist_view_get_exception(mock_hass):
    """Returns HTTP 500 when an unexpected exception occurs in BlocklistView.get."""
    view = BlocklistView()
    request = MagicMock()
    request.app = {"hass": mock_hass}

    with patch(
        "custom_components.google_assistant_entity_console.views.load_blocklist",
        side_effect=RuntimeError("Storage subsystem offline"),
    ):
        resp = await view.get(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data == {"error": "Storage subsystem offline"}


# ===========================================================================
# 3. BlocklistView: POST
# ===========================================================================

@pytest.mark.anyio
async def test_blocklist_view_post_valid_patterns(mock_hass, tmp_path):
    """Accepts and persists valid regex patterns, returning HTTP 200 with updated blocklist."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    view = BlocklistView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}

    valid_patterns = [".*_battery_level$", r"sensor\.weather_.*", r"^media_player\."]
    request.json.return_value = {"blocklist": valid_patterns}

    resp = await view.post(request)
    assert resp.status == 200
    data = json.loads(resp.body.decode())
    assert data == {"success": True, "blocklist": valid_patterns}

    # Verify persistence on disk
    assert load_blocklist(mock_hass) == valid_patterns


@pytest.mark.anyio
async def test_blocklist_view_post_empty_list(mock_hass, tmp_path):
    """Accepts an empty list to clear blocklist, returning HTTP 200."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    save_blocklist(mock_hass, [".*_battery$"])
    assert load_blocklist(mock_hass) == [".*_battery$"]

    view = BlocklistView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"blocklist": []}

    resp = await view.post(request)
    assert resp.status == 200
    data = json.loads(resp.body.decode())
    assert data == {"success": True, "blocklist": []}
    assert load_blocklist(mock_hass) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"blocklist": "not_a_list"},
        {"blocklist": 12345},
        {"blocklist": {"pattern": ".*"}},
        {"blocklist": None},
        {},  # missing blocklist key
        ["directly_a_list"],  # non-dict payload
        "just_a_string",
    ],
)
async def test_blocklist_view_post_rejects_non_list(mock_hass, invalid_payload):
    """Rejects non-list payload with 400 Bad Request ({"error": "Blocklist must be a list"})."""
    view = BlocklistView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = invalid_payload

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert data == {"error": "Blocklist must be a list"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_regex",
    [
        "[unclosed",
        "*dangling",
        "(?P<invalid",
        "(+bad_re",
        "[a-z",
    ],
)
async def test_blocklist_view_post_validates_regex_syntax(mock_hass, invalid_regex):
    """Rejects invalid regex with 400 Bad Request and descriptive error message."""
    view = BlocklistView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"blocklist": ["valid_pattern", invalid_regex]}

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert "error" in data
    assert f"Invalid regex pattern '{invalid_regex}'" in data["error"]


@pytest.mark.anyio
async def test_blocklist_view_post_rejects_non_string_elements(mock_hass):
    """Rejects blocklist containing non-string items with 400 Bad Request."""
    view = BlocklistView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"blocklist": ["valid_pattern", 123]}

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert "error" in data
    assert "Invalid regex pattern '123'" in data["error"]


@pytest.mark.anyio
async def test_blocklist_view_post_handles_unexpected_exception(mock_hass):
    """Returns HTTP 500 when an unexpected exception occurs during update."""
    view = BlocklistView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"blocklist": [".*_battery$"]}

    with patch(
        "custom_components.google_assistant_entity_console.views.save_blocklist",
        side_effect=RuntimeError("Disk write failed"),
    ):
        resp = await view.post(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data == {"error": "Disk write failed"}


# ===========================================================================
# 4. BlocklistAddView: POST
# ===========================================================================

@pytest.mark.anyio
async def test_blocklist_add_view_post_success(mock_hass, tmp_path):
    """Adds valid pattern to blocklist, persists to disk, and returns 200."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    save_blocklist(mock_hass, ["existing_pattern"])

    view = BlocklistAddView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"pattern": r"^sensor\.temp_.*"}

    resp = await view.post(request)
    assert resp.status == 200
    data = json.loads(resp.body.decode())
    assert data == {"success": True, "blocklist": ["existing_pattern", r"^sensor\.temp_.*"]}

    # Verify persistence
    assert load_blocklist(mock_hass) == ["existing_pattern", r"^sensor\.temp_.*"]


@pytest.mark.anyio
async def test_blocklist_add_view_post_prevents_duplicate(mock_hass, tmp_path):
    """Prevents duplicate entries: if pattern exists, does not append duplicate."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)
    existing = [".*_battery_level$", r"^media_player\."]
    save_blocklist(mock_hass, list(existing))

    view = BlocklistAddView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"pattern": ".*_battery_level$"}

    resp = await view.post(request)
    assert resp.status == 200
    data = json.loads(resp.body.decode())
    assert data == {"success": True, "blocklist": existing}

    # Verify no duplicate on disk
    assert load_blocklist(mock_hass) == existing


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_payload",
    [
        {},                      # Missing pattern key
        {"pattern": ""},         # Empty pattern string
        {"pattern": None},       # Null pattern
        {"pattern": 999},        # Non-string pattern
        {"pattern": ["list"]},   # List pattern
        ["not_a_dict"],          # Non-dict body
        "raw_string",            # Raw string body
    ],
)
async def test_blocklist_add_view_post_missing_pattern(mock_hass, invalid_payload):
    """Rejects missing or invalid pattern field with 400 Bad Request."""
    view = BlocklistAddView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = invalid_payload

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert data == {"error": "Missing pattern"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_regex",
    [
        "[unclosed",
        "*dangling",
        "(?P<invalid",
        "(+bad",
    ],
)
async def test_blocklist_add_view_post_invalid_regex(mock_hass, invalid_regex):
    """Rejects invalid regex pattern with 400 Bad Request."""
    view = BlocklistAddView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"pattern": invalid_regex}

    resp = await view.post(request)
    assert resp.status == 400
    data = json.loads(resp.body.decode())
    assert "error" in data
    assert "Invalid regex pattern:" in data["error"]


@pytest.mark.anyio
async def test_blocklist_add_view_post_handles_unexpected_exception(mock_hass):
    """Returns HTTP 500 when an unexpected error occurs during BlocklistAddView.post."""
    view = BlocklistAddView()
    request = AsyncMock()
    request.app = {"hass": mock_hass}
    request.json.return_value = {"pattern": r"^light\."}

    with patch(
        "custom_components.google_assistant_entity_console.views.load_blocklist",
        side_effect=RuntimeError("Read failure"),
    ):
        resp = await view.post(request)
        assert resp.status == 500
        data = json.loads(resp.body.decode())
        assert data == {"error": "Read failure"}


# ===========================================================================
# 5. Real Entity Filtering Against Blocklist Patterns
# ===========================================================================

def test_compiled_blocklist_matching_logic():
    """Verify regex patterns compile and match against sample entity IDs accurately."""
    blocklist_patterns = [
        r".*_battery_level$",
        r"^sensor\.weather_.*",
        r"^media_player\.",
        r"^climate\.guest_room$",
    ]
    compiled = [re.compile(p) for p in blocklist_patterns]

    entities = [
        # Should be blocked
        "sensor.kitchen_battery_level",
        "sensor.bedroom_battery_level",
        "sensor.weather_outdoor",
        "sensor.weather_forecast",
        "media_player.living_room_tv",
        "media_player.kitchen_speaker",
        "climate.guest_room",
        # Should remain visible
        "light.living_room",
        "switch.fan",
        "climate.living_room",
        "vacuum.downstairs",
        "sensor.kitchen_temperature",
    ]

    def is_blocked(entity_id: str) -> bool:
        return any(rx.search(entity_id) for rx in compiled)

    blocked = [e for e in entities if is_blocked(e)]
    visible = [e for e in entities if not is_blocked(e)]

    assert set(blocked) == {
        "sensor.kitchen_battery_level",
        "sensor.bedroom_battery_level",
        "sensor.weather_outdoor",
        "sensor.weather_forecast",
        "media_player.living_room_tv",
        "media_player.kitchen_speaker",
        "climate.guest_room",
    }
    assert set(visible) == {
        "light.living_room",
        "switch.fan",
        "climate.living_room",
        "vacuum.downstairs",
        "sensor.kitchen_temperature",
    }


@pytest.mark.anyio
async def test_async_fetch_entities_data_filters_blocked_entities(mock_hass, tmp_path):
    """Integrates with async_fetch_entities_data to verify blocked entities are excluded."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)

    # Save blocklist pattern
    save_blocklist(mock_hass, [r"^media_player\.", r".*_battery_level$"])

    # Create mock registry entities
    def make_entry(entity_id: str, name: str, device_class: str | None = None):
        entry = MagicMock()
        entry.entity_id = entity_id
        entry.disabled_by = None
        entry.hidden_by = None
        entry.device_id = None
        entry.device_class = device_class
        entry.original_device_class = device_class
        entry.area_id = None
        entry.name = name
        entry.original_name = name
        entry.aliases = []
        entry.options = {}
        entry.platform = "test"
        return entry

    ent_map = {
        "light.living_room": make_entry("light.living_room", "Living Room Light"),
        "switch.fan": make_entry("switch.fan", "Ceiling Fan"),
        "media_player.living_room_tv": make_entry("media_player.living_room_tv", "Living Room TV"),
        "vacuum.robot": make_entry("vacuum.robot", "Roborock Vacuum"),
        # Blocked battery level sensor
        "sensor.smoke_detector_battery_level": make_entry(
            "sensor.smoke_detector_battery_level", "Detector Battery", "battery"
        ),
    }

    mock_ent_reg = MagicMock()
    mock_ent_reg.entities = ent_map

    mock_dev_reg = MagicMock()
    mock_dev_reg.devices = {}

    with (
        patch("custom_components.google_assistant_entity_console.views.entity_registry.async_get", return_value=mock_ent_reg),
        patch("custom_components.google_assistant_entity_console.views.device_registry.async_get", return_value=mock_dev_reg),
        patch("custom_components.google_assistant_entity_console.views.area_registry.async_get", return_value=MagicMock()),
        patch("custom_components.google_assistant_entity_console.views.floor_registry.async_get", return_value=MagicMock()),
        patch("custom_components.google_assistant_entity_console.views.get_current_yaml_filename", return_value="dummy.yaml"),
        patch("custom_components.google_assistant_entity_console.views.load_yaml_exposed_entities", return_value={}),
    ):
        entities = await async_fetch_entities_data(mock_hass)
        returned_ids = {e["entity_id"] for e in entities}

        # Blocked items must not be returned
        assert "media_player.living_room_tv" not in returned_ids
        assert "sensor.smoke_detector_battery_level" not in returned_ids

        # Unblocked items must be present
        assert "light.living_room" in returned_ids
        assert "switch.fan" in returned_ids
        assert "vacuum.robot" in returned_ids


@pytest.mark.anyio
async def test_async_fetch_entities_data_handles_corrupted_blocklist_regex(mock_hass, tmp_path):
    """Gracefully skips invalid regex stored in blocklist without failing entity fetch."""
    mock_hass.config.path.side_effect = lambda filename: str(tmp_path / filename)

    # Save invalid pattern alongside a valid pattern
    save_blocklist(mock_hass, ["[unclosed_pattern", r"^switch\.fan$"])

    def make_entry(entity_id: str, name: str):
        entry = MagicMock()
        entry.entity_id = entity_id
        entry.disabled_by = None
        entry.hidden_by = None
        entry.device_id = None
        entry.device_class = None
        entry.original_device_class = None
        entry.area_id = None
        entry.name = name
        entry.original_name = name
        entry.aliases = []
        entry.options = {}
        entry.platform = "test"
        return entry

    ent_map = {
        "light.kitchen": make_entry("light.kitchen", "Kitchen Light"),
        "switch.fan": make_entry("switch.fan", "Exhaust Fan"),
    }

    mock_ent_reg = MagicMock()
    mock_ent_reg.entities = ent_map

    mock_dev_reg = MagicMock()
    mock_dev_reg.devices = {}

    with (
        patch("custom_components.google_assistant_entity_console.views.entity_registry.async_get", return_value=mock_ent_reg),
        patch("custom_components.google_assistant_entity_console.views.device_registry.async_get", return_value=mock_dev_reg),
        patch("custom_components.google_assistant_entity_console.views.area_registry.async_get", return_value=MagicMock()),
        patch("custom_components.google_assistant_entity_console.views.floor_registry.async_get", return_value=MagicMock()),
        patch("custom_components.google_assistant_entity_console.views.get_current_yaml_filename", return_value="dummy.yaml"),
        patch("custom_components.google_assistant_entity_console.views.load_yaml_exposed_entities", return_value={}),
    ):
        entities = await async_fetch_entities_data(mock_hass)
        returned_ids = {e["entity_id"] for e in entities}

        # Invalid regex was ignored, valid regex blocked switch.fan
        assert "switch.fan" not in returned_ids
        assert "light.kitchen" in returned_ids
