"""Tests for YAML serialization, custom tag representers, and loader round-trips."""

from __future__ import annotations

import io

import pytest
import yaml

from custom_components.google_assistant_entity_console.views import (
    Include,
    Secret,
    include_representer,
    load_yaml_exposed_entities,
    secret_representer,
)


def test_secret_init_and_attributes() -> None:
    """Test Secret class initialization and value attribute."""
    sec = Secret("test_secret_token_123")
    assert sec.value == "test_secret_token_123"


def test_include_init_and_attributes() -> None:
    """Test Include class initialization and value attribute."""
    inc = Include("sub_config.yaml")
    assert inc.value == "sub_config.yaml"


def test_secret_representer_direct() -> None:
    """Test secret_representer directly produces a scalar node with !secret tag."""
    dumper = yaml.SafeDumper(io.StringIO())
    node = secret_representer(dumper, Secret("homeassistant_secret"))
    assert node.tag == "!secret"
    assert node.value == "homeassistant_secret"


def test_include_representer_direct() -> None:
    """Test include_representer directly produces a scalar node with !include tag."""
    dumper = yaml.SafeDumper(io.StringIO())
    node = include_representer(dumper, Include("my_includes/lights.yaml"))
    assert node.tag == "!include"
    assert node.value == "my_includes/lights.yaml"


def test_yaml_dump_secret_and_include_tags() -> None:
    """Test dumping structures containing Secret and Include produces expected YAML tags."""
    config_dict = {
        "project_id": Secret("googleassistant_projectName"),
        "service_account": Include("SERVICE_ACCOUNT.json"),
        "report_state": True,
        "expose_by_default": False,
    }
    dumped = yaml.dump(config_dict, Dumper=yaml.SafeDumper, sort_keys=False)

    assert "!secret" in dumped
    assert "googleassistant_projectName" in dumped
    assert "!include" in dumped
    assert "SERVICE_ACCOUNT.json" in dumped


def test_yaml_dump_nested_structures() -> None:
    """Test dumping nested dictionaries and lists with Secret and Include instances."""
    nested_data = {
        "google_assistant": {
            "credentials": {
                "client_secret": Secret("sec_999"),
                "account_file": Include("accounts/test.json"),
            },
            "enabled": True,
        }
    }
    dumped = yaml.dump(nested_data, Dumper=yaml.SafeDumper, sort_keys=False)
    assert "!secret" in dumped
    assert "sec_999" in dumped
    assert "!include" in dumped
    assert "accounts/test.json" in dumped


@pytest.mark.anyio
async def test_load_yaml_exposed_entities_none_and_empty_filename(mock_hass) -> None:
    """Test load_yaml_exposed_entities returns empty dict when filename is None or empty."""
    assert await load_yaml_exposed_entities(mock_hass, None) == {}
    assert await load_yaml_exposed_entities(mock_hass, "") == {}


@pytest.mark.anyio
async def test_load_yaml_exposed_entities_file_not_found(mock_hass, tmp_path) -> None:
    """Test load_yaml_exposed_entities returns empty dict when file does not exist."""
    mock_hass.config.path.side_effect = lambda f: str(tmp_path / f)
    result = await load_yaml_exposed_entities(mock_hass, "non_existent_file.yaml")
    assert result == {}


@pytest.mark.anyio
async def test_load_yaml_exposed_entities_empty_file(mock_hass, tmp_path) -> None:
    """Test load_yaml_exposed_entities returns empty dict on an empty 0-byte file."""
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("", encoding="utf-8")
    mock_hass.config.path.side_effect = lambda f: str(tmp_path / f)

    result = await load_yaml_exposed_entities(mock_hass, "empty.yaml")
    assert result == {}


@pytest.mark.anyio
async def test_load_yaml_exposed_entities_malformed_yaml(mock_hass, tmp_path) -> None:
    """Test load_yaml_exposed_entities returns empty dict on syntactically invalid YAML."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("entity_config: [unclosed list: {mapping", encoding="utf-8")
    mock_hass.config.path.side_effect = lambda f: str(tmp_path / f)

    result = await load_yaml_exposed_entities(mock_hass, "bad.yaml")
    assert result == {}


@pytest.mark.anyio
async def test_load_yaml_exposed_entities_non_dict_yaml(mock_hass, tmp_path) -> None:
    """Test load_yaml_exposed_entities returns empty dict when YAML parses into non-dict."""
    list_yaml = tmp_path / "list.yaml"
    list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
    mock_hass.config.path.side_effect = lambda f: str(tmp_path / f)

    result = await load_yaml_exposed_entities(mock_hass, "list.yaml")
    assert result == {}


@pytest.mark.anyio
async def test_load_yaml_exposed_entities_real_config(mock_hass, tmp_path) -> None:
    """Test loading and parsing realistic Google Assistant configuration file."""
    yaml_content = """# Google Assistant Generated Configuration
project_id: !secret googleassistant_projectName
service_account: !include service_account.json
report_state: true
expose_by_default: false

entity_config:
  light.kitchen_pendant:
    expose: true
    name: "Kitchen Pendant Light"
    aliases:
      - "Kitchen Light"
      - "Pendant"
    room: "Kitchen"

  switch.garden_fountain:
    expose: false
    name: "Garden Fountain"
    aliases:
      - "Fountain"
    room: "Garden"

  climate.hallway_thermostat:
    expose: true
    name: "Main Thermostat"
    room: "Hallway"

  sensor.outdoor_temperature:
    name: "Outdoor Temp"
    room: "Patio"

  cover.garage_door:
    expose: true

  media_player.living_room_tv: "invalid_scalar_config"
"""
    yaml_file = tmp_path / "gaGen_123456.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")
    mock_hass.config.path.side_effect = lambda f: str(tmp_path / f)

    exposed = await load_yaml_exposed_entities(mock_hass, "gaGen_123456.yaml")

    # Exposed light with full details
    assert "light.kitchen_pendant" in exposed
    assert exposed["light.kitchen_pendant"] == {
        "name": "Kitchen Pendant Light",
        "aliases": ["Kitchen Light", "Pendant"],
        "room": "Kitchen",
    }

    # Unexposed switch (expose: false) must be excluded
    assert "switch.garden_fountain" not in exposed

    # Exposed climate with no aliases defaults aliases to empty list
    assert "climate.hallway_thermostat" in exposed
    assert exposed["climate.hallway_thermostat"] == {
        "name": "Main Thermostat",
        "aliases": [],
        "room": "Hallway",
    }

    # Sensor without expose field must be excluded
    assert "sensor.outdoor_temperature" not in exposed

    # Cover with expose: true but missing optional name/aliases/room defaults properly
    assert "cover.garage_door" in exposed
    assert exposed["cover.garage_door"] == {
        "name": None,
        "aliases": [],
        "room": None,
    }

    # Malformed entity config (scalar instead of dict) must be skipped
    assert "media_player.living_room_tv" not in exposed


@pytest.mark.anyio
async def test_yaml_roundtrip_serialization_and_deserialization(mock_hass, tmp_path) -> None:
    """Test end-to-end roundtrip: dump entities with SafeDumper, load with load_yaml_exposed_entities."""
    entities_to_expose = {
        "light.living_room_ceiling": {
            "expose": True,
            "name": "Living Room Ceiling",
            "aliases": ["Ceiling", "Main Living Light"],
            "room": "Living Room",
        },
        "switch.coffee_maker": {
            "expose": True,
            "name": "Coffee Maker",
            "aliases": ["Espresso Machine"],
            "room": "Kitchen",
        },
        "lock.front_door": {
            "expose": True,
            "name": "Front Door Lock",
            "aliases": [],
            "room": "Entrance",
        },
        "sensor.hidden_sensor": {
            "expose": False,
            "name": "Hidden Sensor",
        },
    }

    full_yaml_doc = {
        "project_id": Secret("googleassistant_projectName"),
        "service_account": Include("SERVICE_ACCOUNT.json"),
        "report_state": True,
        "expose_by_default": False,
        "entity_config": entities_to_expose,
    }

    dumped_str = yaml.dump(full_yaml_doc, Dumper=yaml.SafeDumper, sort_keys=False)

    test_file = tmp_path / "gaGen_999999.yaml"
    test_file.write_text(dumped_str, encoding="utf-8")
    mock_hass.config.path.side_effect = lambda f: str(tmp_path / f)

    loaded_exposed = await load_yaml_exposed_entities(mock_hass, "gaGen_999999.yaml")

    assert len(loaded_exposed) == 3
    assert "sensor.hidden_sensor" not in loaded_exposed

    assert loaded_exposed["light.living_room_ceiling"] == {
        "name": "Living Room Ceiling",
        "aliases": ["Ceiling", "Main Living Light"],
        "room": "Living Room",
    }
    assert loaded_exposed["switch.coffee_maker"] == {
        "name": "Coffee Maker",
        "aliases": ["Espresso Machine"],
        "room": "Kitchen",
    }
    assert loaded_exposed["lock.front_door"] == {
        "name": "Front Door Lock",
        "aliases": [],
        "room": "Entrance",
    }
