"""Comprehensive tests for async_fetch_entities_data in Google Assistant Entity Console.

Covers:
1. Supported vs. Unsupported Domain Filtering
2. Device Class Filtering for Binary Sensors, Sensors, and Events
3. Hidden and Disabled Entity Filtering
4. Light Group Detection and Group Membership
5. Regex Blocklist Exclusion and Regex Error Handling
6. Display Name Resolution Hierarchy and COMPUTED_NAME Singleton Fallback
7. Area and Floor Hierarchy Resolution
8. Conversation Options, YAML Exposure, Aliases Sanitization, and State Availability
9. Full Payload Schema and Combined Integration Verification
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.google_assistant_entity_console.views import (
    async_fetch_entities_data,
)


class MockComputedNameType:
    """Mock Home Assistant COMPUTED_NAME sentinel object."""

    def __str__(self) -> str:
        return "<ComputedNameType._singleton: 0>"

    def __repr__(self) -> str:
        return "<ComputedNameType._singleton: 0>"


def make_entity_entry(
    entity_id: str,
    *,
    name: Any = None,
    original_name: Any = None,
    device_id: str | None = None,
    area_id: str | None = None,
    device_class: str | None = None,
    original_device_class: str | None = None,
    disabled_by: str | None = None,
    hidden_by: str | None = None,
    aliases: list[Any] | None = None,
    options: dict[str, Any] | None = None,
    platform: str = "test_platform",
) -> MagicMock:
    """Construct a mock RegistryEntry matching Home Assistant's entity registry."""
    entry = MagicMock()
    entry.entity_id = entity_id
    entry.name = name
    entry.original_name = original_name
    entry.device_id = device_id
    entry.area_id = area_id
    entry.device_class = device_class
    entry.original_device_class = original_device_class
    entry.disabled_by = disabled_by
    entry.hidden_by = hidden_by
    entry.aliases = aliases
    entry.options = options if options is not None else {}
    entry.platform = platform
    return entry


def make_device(
    device_id: str,
    *,
    name: Any = None,
    name_by_user: Any = None,
    area_id: str | None = None,
) -> MagicMock:
    """Construct a mock DeviceEntry matching Home Assistant's device registry."""
    dev = MagicMock()
    dev.id = device_id
    dev.name = name
    dev.name_by_user = name_by_user
    dev.area_id = area_id
    return dev


def make_area(area_id: str, name: str, floor_id: str | None = None) -> MagicMock:
    """Construct a mock AreaEntry matching Home Assistant's area registry."""
    area = MagicMock()
    area.id = area_id
    area.name = name
    area.floor_id = floor_id
    return area


def make_floor(floor_id: str, name: str) -> MagicMock:
    """Construct a mock FloorEntry matching Home Assistant's floor registry."""
    floor = MagicMock()
    floor.floor_id = floor_id
    floor.name = name
    return floor


def make_state(
    entity_id: str,
    state: str = "on",
    attributes: dict[str, Any] | None = None,
) -> MagicMock:
    """Construct a mock State matching Home Assistant's state object."""
    st = MagicMock()
    st.entity_id = entity_id
    st.state = state
    st.attributes = attributes if attributes is not None else {}
    return st


def setup_hass_states(
    mock_hass: MagicMock,
    *,
    states: dict[str, Any] | None = None,
    light_states: list[Any] | None = None,
    group_states: list[Any] | None = None,
) -> None:
    """Wire mock_hass state lookup and async_all queries."""
    states_dict = states or {}
    light_list = light_states if light_states is not None else []
    group_list = group_states if group_states is not None else []

    def async_all_mock(domain: str | None = None):
        if domain == "light":
            return light_list
        if domain == "group":
            return group_list
        return list(states_dict.values())

    mock_hass.states.async_all = MagicMock(side_effect=async_all_mock)
    mock_hass.states.get = MagicMock(side_effect=lambda eid: states_dict.get(eid))


async def run_fetch_entities(
    hass: MagicMock,
    *,
    entities: dict[str, Any] | list[Any] | None = None,
    devices: dict[str, Any] | list[Any] | None = None,
    areas: list[Any] | None = None,
    floors: list[Any] | None = None,
    yaml_exposed: dict[str, Any] | None = None,
    blocklist: list[str] | None = None,
    states: dict[str, Any] | None = None,
    light_states: list[Any] | None = None,
    group_states: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Execute async_fetch_entities_data with isolated mock registries and environment."""
    ent_map = {}
    if isinstance(entities, dict):
        ent_map = entities
    elif isinstance(entities, list):
        ent_map = {e.entity_id: e for e in entities}

    dev_map = {}
    if isinstance(devices, dict):
        dev_map = devices
    elif isinstance(devices, list):
        dev_map = {d.id: d for d in devices}

    mock_ent_reg = MagicMock()
    mock_ent_reg.entities = ent_map

    mock_dev_reg = MagicMock()
    mock_dev_reg.devices = dev_map

    mock_area_reg = MagicMock()
    mock_area_reg.async_list_areas = MagicMock(return_value=areas or [])

    mock_floor_reg = MagicMock()
    mock_floor_reg.async_list_floors = MagicMock(return_value=floors or [])

    setup_hass_states(
        hass,
        states=states,
        light_states=light_states,
        group_states=group_states,
    )

    with (
        patch(
            "custom_components.google_assistant_entity_console.views.entity_registry.async_get",
            return_value=mock_ent_reg,
        ),
        patch(
            "custom_components.google_assistant_entity_console.views.device_registry.async_get",
            return_value=mock_dev_reg,
        ),
        patch(
            "custom_components.google_assistant_entity_console.views.area_registry.async_get",
            return_value=mock_area_reg,
        ),
        patch(
            "custom_components.google_assistant_entity_console.views.floor_registry.async_get",
            return_value=mock_floor_reg,
        ),
        patch(
            "custom_components.google_assistant_entity_console.views.get_current_yaml_filename",
            return_value="configuration.yaml",
        ),
        patch(
            "custom_components.google_assistant_entity_console.views.load_yaml_exposed_entities",
            return_value=yaml_exposed or {},
        ),
        patch(
            "custom_components.google_assistant_entity_console.views.load_blocklist",
            return_value=blocklist or [],
        ),
    ):
        return await async_fetch_entities_data(hass)


# ===========================================================================
# 1. Supported vs Unsupported Domain Filtering
# ===========================================================================

SUPPORTED_DOMAINS = [
    "alarm_control_panel",
    "button",
    "camera",
    "climate",
    "cover",
    "fan",
    "group",
    "humidifier",
    "input_boolean",
    "input_button",
    "input_select",
    "lawn_mower",
    "light",
    "lock",
    "media_player",
    "scene",
    "script",
    "select",
    "switch",
    "vacuum",
    "valve",
    "water_heater",
]

UNSUPPORTED_DOMAINS = [
    "automation",
    "zone",
    "sun",
    "weather",
    "person",
    "timer",
    "counter",
    "input_number",
    "input_text",
    "input_datetime",
    "update",
    "remote",
    "siren",
    "notify",
    "datetime",
    "date",
    "time",
    "tts",
    "device_tracker",
]


@pytest.mark.anyio
@pytest.mark.parametrize("domain", SUPPORTED_DOMAINS)
async def test_supported_domain_is_included(mock_hass, domain):
    """Verify that all 22 officially supported domains are included by default."""
    eid = f"{domain}.test_entity"
    entry = make_entity_entry(eid, name=f"Test {domain}")

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 1
    assert result[0]["entity_id"] == eid
    assert result[0]["domain"] == domain


@pytest.mark.anyio
@pytest.mark.parametrize("domain", UNSUPPORTED_DOMAINS)
async def test_unsupported_domain_is_excluded(mock_hass, domain):
    """Verify that unsupported domains are filtered out and omitted from the payload."""
    eid = f"{domain}.test_entity"
    entry = make_entity_entry(eid, name=f"Test {domain}")

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 0


@pytest.mark.anyio
async def test_mixed_supported_and_unsupported_domains(mock_hass):
    """Verify that in a large mixed registry, only supported entities survive filtering."""
    supported_entries = [
        make_entity_entry(f"{d}.entity_{i}", name=f"{d} {i}")
        for i, d in enumerate(SUPPORTED_DOMAINS)
    ]
    unsupported_entries = [
        make_entity_entry(f"{d}.entity_{i}", name=f"{d} {i}")
        for i, d in enumerate(UNSUPPORTED_DOMAINS)
    ]
    all_entries = supported_entries + unsupported_entries

    result = await run_fetch_entities(mock_hass, entities=all_entries)
    returned_ids = {e["entity_id"] for e in result}

    for entry in supported_entries:
        assert entry.entity_id in returned_ids
    for entry in unsupported_entries:
        assert entry.entity_id not in returned_ids

    assert len(result) == len(SUPPORTED_DOMAINS)


# ===========================================================================
# 2. Device Class Filtering for Binary Sensors, Sensors, and Events
# ===========================================================================

BINARY_SENSOR_SUPPORTED_CLASSES = [
    "carbon_monoxide",
    "door",
    "garage_door",
    "lock",
    "moisture",
    "opening",
    "smoke",
    "window",
]

BINARY_SENSOR_UNSUPPORTED_CLASSES = [
    "battery",
    "battery_charging",
    "cold",
    "connectivity",
    "gas",
    "heat",
    "light",
    "motion",
    "moving",
    "occupancy",
    "plug",
    "power",
    "presence",
    "problem",
    "running",
    "safety",
    "sound",
    "tamper",
    "vibration",
    "",
    None,
]

SENSOR_SUPPORTED_CLASSES = [
    "aqi",
    "carbon_dioxide",
    "carbon_monoxide",
    "humidity",
    "pm10",
    "pm25",
    "temperature",
    "volatile_organic_compounds",
]

SENSOR_UNSUPPORTED_CLASSES = [
    "apparent_temperature",
    "atmospheric_pressure",
    "battery",
    "current",
    "data_rate",
    "data_size",
    "date",
    "distance",
    "duration",
    "energy",
    "energy_storage",
    "frequency",
    "gas",
    "illuminance",
    "irradiance",
    "monetary",
    "nitrogen_dioxide",
    "nitrogen_monoxide",
    "nitrous_oxide",
    "ozone",
    "ph",
    "power",
    "power_factor",
    "precipitation",
    "precipitation_intensity",
    "pressure",
    "reactive_power",
    "signal_strength",
    "sound_pressure",
    "speed",
    "sulfur_dioxide",
    "voltage",
    "volume",
    "volume_flow_rate",
    "volume_storage",
    "water",
    "weight",
    "wind_speed",
    "",
    None,
]


@pytest.mark.anyio
@pytest.mark.parametrize("dev_cls", BINARY_SENSOR_SUPPORTED_CLASSES)
async def test_binary_sensor_supported_device_class_included(mock_hass, dev_cls):
    """Verify binary_sensor with supported device_class is included."""
    eid = f"binary_sensor.test_{dev_cls}"
    entry = make_entity_entry(eid, device_class=dev_cls, name=f"BS {dev_cls}")

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 1
    assert result[0]["entity_id"] == eid
    assert result[0]["device_class"] == dev_cls
    assert result[0]["domain"] == "binary_sensor"


@pytest.mark.anyio
@pytest.mark.parametrize("dev_cls", BINARY_SENSOR_UNSUPPORTED_CLASSES)
async def test_binary_sensor_unsupported_device_class_excluded(mock_hass, dev_cls):
    """Verify binary_sensor with unsupported or empty device_class is excluded."""
    eid = f"binary_sensor.unsupported_{dev_cls}"
    entry = make_entity_entry(eid, device_class=dev_cls, name=f"BS {dev_cls}")

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 0


@pytest.mark.anyio
@pytest.mark.parametrize("dev_cls", SENSOR_SUPPORTED_CLASSES)
async def test_sensor_supported_device_class_included(mock_hass, dev_cls):
    """Verify sensor with supported device_class is included."""
    eid = f"sensor.test_{dev_cls}"
    entry = make_entity_entry(eid, device_class=dev_cls, name=f"Sensor {dev_cls}")

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 1
    assert result[0]["entity_id"] == eid
    assert result[0]["device_class"] == dev_cls
    assert result[0]["domain"] == "sensor"


@pytest.mark.anyio
@pytest.mark.parametrize("dev_cls", SENSOR_UNSUPPORTED_CLASSES)
async def test_sensor_unsupported_device_class_excluded(mock_hass, dev_cls):
    """Verify sensor with unsupported or empty device_class is excluded."""
    eid = f"sensor.unsupported_{dev_cls}"
    entry = make_entity_entry(eid, device_class=dev_cls, name=f"Sensor {dev_cls}")

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 0


@pytest.mark.anyio
async def test_event_domain_device_class_filtering(mock_hass):
    """Verify event domain is only included when device_class == 'doorbell'."""
    doorbell_event = make_entity_entry(
        "event.front_door_bell",
        device_class="doorbell",
        name="Front Doorbell",
    )
    button_event = make_entity_entry(
        "event.smart_button",
        device_class="button",
        name="Smart Button",
    )
    motion_event = make_entity_entry(
        "event.porch_motion",
        device_class="motion",
        name="Porch Motion",
    )
    none_event = make_entity_entry(
        "event.generic_event",
        device_class=None,
        name="Generic Event",
    )

    result = await run_fetch_entities(
        mock_hass,
        entities=[doorbell_event, button_event, motion_event, none_event],
    )
    assert len(result) == 1
    assert result[0]["entity_id"] == "event.front_door_bell"
    assert result[0]["device_class"] == "doorbell"


@pytest.mark.anyio
async def test_original_device_class_fallback(mock_hass):
    """Verify device class filtering falls back to original_device_class when device_class is unset."""
    # Supported binary_sensor using original_device_class
    bs_entry = make_entity_entry(
        "binary_sensor.garage_contact",
        device_class=None,
        original_device_class="garage_door",
        name="Garage Contact",
    )
    # Supported sensor using original_device_class
    sensor_entry = make_entity_entry(
        "sensor.attic_temp",
        device_class="",
        original_device_class="temperature",
        name="Attic Temperature",
    )
    # Supported event using original_device_class
    event_entry = make_entity_entry(
        "event.back_doorbell",
        device_class=None,
        original_device_class="doorbell",
        name="Back Doorbell",
    )
    # Unsupported binary_sensor using original_device_class
    bs_unsupported = make_entity_entry(
        "binary_sensor.motion_hallway",
        device_class=None,
        original_device_class="motion",
        name="Hallway Motion",
    )
    # Unsupported sensor using original_device_class
    sensor_unsupported = make_entity_entry(
        "sensor.battery_gauge",
        device_class=None,
        original_device_class="battery",
        name="Battery Gauge",
    )

    result = await run_fetch_entities(
        mock_hass,
        entities=[
            bs_entry,
            sensor_entry,
            event_entry,
            bs_unsupported,
            sensor_unsupported,
        ],
    )
    returned_ids = {e["entity_id"] for e in result}
    assert returned_ids == {
        "binary_sensor.garage_contact",
        "sensor.attic_temp",
        "event.back_doorbell",
    }


# ===========================================================================
# 3. Filtering Hidden and Disabled Entities
# ===========================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "disabled_reason",
    ["user", "integration", "config_entry"],
)
async def test_disabled_entities_are_excluded(mock_hass, disabled_reason):
    """Verify entities with any disabled_by reason are strictly excluded."""
    entry = make_entity_entry(
        "light.kitchen_disabled",
        disabled_by=disabled_reason,
        hidden_by=None,
        name="Kitchen Light",
    )
    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 0


@pytest.mark.anyio
@pytest.mark.parametrize("hidden_reason", ["user", "integration"])
async def test_hidden_entities_are_excluded(mock_hass, hidden_reason):
    """Verify entities with any hidden_by reason are strictly excluded."""
    entry = make_entity_entry(
        "light.kitchen_hidden",
        disabled_by=None,
        hidden_by=hidden_reason,
        name="Kitchen Light",
    )
    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 0


@pytest.mark.anyio
async def test_entity_with_both_disabled_and_hidden_is_excluded(mock_hass):
    """Verify entity with both disabled_by and hidden_by set is excluded."""
    entry = make_entity_entry(
        "switch.basement_pump",
        disabled_by="user",
        hidden_by="user",
        name="Basement Pump",
    )
    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 0


@pytest.mark.anyio
async def test_active_entities_neither_hidden_nor_disabled_are_retained(mock_hass):
    """Verify active entities with None for both disabled_by and hidden_by are retained."""
    entry = make_entity_entry(
        "light.kitchen_active",
        disabled_by=None,
        hidden_by=None,
        name="Active Kitchen Light",
    )
    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert len(result) == 1
    assert result[0]["entity_id"] == "light.kitchen_active"


# ===========================================================================
# 4. Light Group Detection and Group Membership
# ===========================================================================

@pytest.mark.anyio
async def test_light_group_detection_from_light_domain(mock_hass):
    """Verify members of light group entities receive in_group=True, non-members receive False."""
    bulb_1 = make_entity_entry("light.chandelier_1", name="Chandelier 1")
    bulb_2 = make_entity_entry("light.chandelier_2", name="Chandelier 2")
    bulb_solo = make_entity_entry("light.desk_lamp", name="Desk Lamp")

    light_group_state = make_state(
        "light.chandelier_group",
        state="on",
        attributes={"entity_ids": ["light.chandelier_1", "light.chandelier_2"]},
    )

    result = await run_fetch_entities(
        mock_hass,
        entities=[bulb_1, bulb_2, bulb_solo],
        light_states=[light_group_state],
    )
    res_map = {e["entity_id"]: e for e in result}

    assert res_map["light.chandelier_1"]["in_group"] is True
    assert res_map["light.chandelier_2"]["in_group"] is True
    assert res_map["light.desk_lamp"]["in_group"] is False


@pytest.mark.anyio
async def test_light_group_detection_from_group_domain(mock_hass):
    """Verify generic group entities only mark light members with in_group=True."""
    light_strip_1 = make_entity_entry("light.strip_left", name="Strip Left")
    light_strip_2 = make_entity_entry("light.strip_right", name="Strip Right")
    switch_fan = make_entity_entry("switch.exhaust_fan", name="Exhaust Fan")

    # Generic group containing both lights and a switch
    generic_group_state = make_state(
        "group.living_room_group",
        state="on",
        attributes={
            "entity_ids": [
                "light.strip_left",
                "switch.exhaust_fan",
                "light.strip_right",
            ]
        },
    )

    result = await run_fetch_entities(
        mock_hass,
        entities=[light_strip_1, light_strip_2, switch_fan],
        group_states=[generic_group_state],
    )
    res_map = {e["entity_id"]: e for e in result}

    # Only members starting with "light." are tagged as light_group_members
    assert res_map["light.strip_left"]["in_group"] is True
    assert res_map["light.strip_right"]["in_group"] is True
    assert res_map["switch.exhaust_fan"]["in_group"] is False


@pytest.mark.anyio
async def test_group_detection_robustness_malformed_attributes(mock_hass):
    """Verify group parsing handles None attributes, missing entity_ids, and non-list entity_ids gracefully."""
    light_entry = make_entity_entry("light.test_light", name="Test Light")

    malformed_states = [
        make_state("light.none_attr", attributes=None),
        make_state("light.empty_attr", attributes={}),
        make_state("light.string_attr", attributes={"entity_ids": "light.test_light"}),
        make_state("light.int_attr", attributes={"entity_ids": 12345}),
        make_state("light.dict_attr", attributes={"entity_ids": {"id": "light.test_light"}}),
        make_state("group.none_attr", attributes=None),
        make_state("group.string_attr", attributes={"entity_ids": "light.test_light"}),
    ]

    result = await run_fetch_entities(
        mock_hass,
        entities=[light_entry],
        light_states=malformed_states[:5],
        group_states=malformed_states[5:],
    )
    assert len(result) == 1
    assert result[0]["entity_id"] == "light.test_light"
    assert result[0]["in_group"] is False


# ===========================================================================
# 5. Regex Blocklist Exclusion
# ===========================================================================

@pytest.mark.anyio
async def test_regex_blocklist_exact_and_wildcard_patterns(mock_hass):
    """Verify entities matching blocklist regexes are filtered out while others remain."""
    blocklist = [
        r"^light\.secret_bulb$",
        r".*_private$",
        r"^climate\.attic_.*",
    ]

    e_secret = make_entity_entry("light.secret_bulb", name="Secret Bulb")
    e_private = make_entity_entry("switch.bedroom_private", name="Private Switch")
    e_attic_ac = make_entity_entry("climate.attic_ac", name="Attic AC")
    e_attic_fan = make_entity_entry("fan.attic_exhaust", name="Attic Fan")  # domain is fan, not climate.attic_
    e_living_room = make_entity_entry("light.living_room", name="Living Room")

    result = await run_fetch_entities(
        mock_hass,
        entities=[e_secret, e_private, e_attic_ac, e_attic_fan, e_living_room],
        blocklist=blocklist,
    )
    returned_ids = {e["entity_id"] for e in result}

    assert "light.secret_bulb" not in returned_ids
    assert "switch.bedroom_private" not in returned_ids
    assert "climate.attic_ac" not in returned_ids
    assert "fan.attic_exhaust" in returned_ids
    assert "light.living_room" in returned_ids


@pytest.mark.anyio
async def test_regex_blocklist_corrupted_pattern_tolerated(mock_hass):
    """Verify corrupted regex patterns in blocklist are skipped and do not abort fetching."""
    blocklist = [
        "[invalid-bracket",
        "(?P<incomplete",
        r"^light\.blocked_light$",
    ]

    e_blocked = make_entity_entry("light.blocked_light", name="Blocked Light")
    e_allowed = make_entity_entry("light.allowed_light", name="Allowed Light")

    result = await run_fetch_entities(
        mock_hass,
        entities=[e_blocked, e_allowed],
        blocklist=blocklist,
    )
    returned_ids = {e["entity_id"] for e in result}

    assert "light.blocked_light" not in returned_ids
    assert "light.allowed_light" in returned_ids


# ===========================================================================
# 6. Display Name Resolution Hierarchy & COMPUTED_NAME Fallback
# ===========================================================================

@pytest.mark.anyio
async def test_display_name_hierarchy_entry_name(mock_hass):
    """1. Explicit entry.name (string) takes highest priority."""
    device = make_device("dev_1", name_by_user="User Dev", name="Raw Dev")
    entry = make_entity_entry(
        "light.kitchen",
        name="Custom Override Name",
        original_name="Original Name",
        device_id="dev_1",
    )

    result = await run_fetch_entities(mock_hass, entities=[entry], devices=[device])
    assert result[0]["display_name"] == "Custom Override Name"


@pytest.mark.anyio
async def test_display_name_hierarchy_device_name_by_user(mock_hass):
    """2. When entry.name is None/empty, falls back to device.name_by_user."""
    device = make_device("dev_1", name_by_user="User Device Name", name="Raw Dev")
    entry = make_entity_entry(
        "light.kitchen",
        name=None,
        original_name="Original Name",
        device_id="dev_1",
    )

    result = await run_fetch_entities(mock_hass, entities=[entry], devices=[device])
    assert result[0]["display_name"] == "User Device Name"


@pytest.mark.anyio
async def test_display_name_hierarchy_device_name(mock_hass):
    """3. When device.name_by_user is None, falls back to device.name."""
    device = make_device("dev_1", name_by_user=None, name="Raw Device Name")
    entry = make_entity_entry(
        "light.kitchen",
        name=None,
        original_name="Original Name",
        device_id="dev_1",
    )

    result = await run_fetch_entities(mock_hass, entities=[entry], devices=[device])
    assert result[0]["display_name"] == "Raw Device Name"


@pytest.mark.anyio
async def test_display_name_hierarchy_original_name(mock_hass):
    """4. When no device exists, falls back to entry.original_name."""
    entry = make_entity_entry(
        "light.kitchen",
        name=None,
        original_name="Original Manufacturer Name",
        device_id=None,
    )

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert result[0]["display_name"] == "Original Manufacturer Name"


@pytest.mark.anyio
async def test_display_name_hierarchy_formatted_entity_id_fallback(mock_hass):
    """5. When all name attributes are None, formats entity_id name part into title case."""
    entry = make_entity_entry(
        "light.master_bedroom_overhead_spot",
        name=None,
        original_name=None,
        device_id=None,
    )

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert result[0]["display_name"] == "Master Bedroom Overhead Spot"


@pytest.mark.anyio
async def test_display_name_computed_name_singleton_full_fallback(mock_hass):
    """Verify non-string COMPUTED_NAME singleton objects gracefully fall back to formatted entity ID."""
    computed_name_obj = MockComputedNameType()

    device = make_device(
        "dev_computed",
        name_by_user=computed_name_obj,
        name=computed_name_obj,
    )
    entry = make_entity_entry(
        "climate.living_room_thermostat",
        name=computed_name_obj,
        original_name=computed_name_obj,
        device_id="dev_computed",
    )

    result = await run_fetch_entities(mock_hass, entities=[entry], devices=[device])
    assert len(result) == 1
    assert result[0]["display_name"] == "Living Room Thermostat"


@pytest.mark.anyio
async def test_display_name_empty_string_falls_back(mock_hass):
    """Verify empty string names ('') are treated as unset and trigger hierarchy fallbacks."""
    device = make_device("dev_empty", name_by_user="", name="Fallback Device Name")
    entry = make_entity_entry(
        "switch.porch_light",
        name="",
        original_name="Original Switch Name",
        device_id="dev_empty",
    )

    result = await run_fetch_entities(mock_hass, entities=[entry], devices=[device])
    assert result[0]["display_name"] == "Fallback Device Name"


# ===========================================================================
# 7. Area and Floor Hierarchy Resolution
# ===========================================================================

@pytest.mark.anyio
async def test_area_and_floor_resolved_from_entity(mock_hass):
    """Verify area and floor are resolved directly from entry.area_id."""
    area = make_area("kitchen_area", "Kitchen", floor_id="ground_floor")
    floor = make_floor("ground_floor", "Ground Floor")
    entry = make_entity_entry("light.kitchen_main", area_id="kitchen_area")

    result = await run_fetch_entities(
        mock_hass,
        entities=[entry],
        areas=[area],
        floors=[floor],
    )
    assert result[0]["area"] == "Kitchen"
    assert result[0]["floor"] == "Ground Floor"


@pytest.mark.anyio
async def test_area_and_floor_fallback_to_device(mock_hass):
    """Verify when entry.area_id is None, area and floor fall back to device.area_id."""
    area = make_area("office_area", "Home Office", floor_id="upstairs")
    floor = make_floor("upstairs", "Second Floor")
    device = make_device("dev_office", area_id="office_area")
    entry = make_entity_entry("light.desk_light", area_id=None, device_id="dev_office")

    result = await run_fetch_entities(
        mock_hass,
        entities=[entry],
        devices=[device],
        areas=[area],
        floors=[floor],
    )
    assert result[0]["area"] == "Home Office"
    assert result[0]["floor"] == "Second Floor"


@pytest.mark.anyio
async def test_entity_area_overrides_device_area(mock_hass):
    """Verify entry.area_id takes precedence over device.area_id."""
    area_entity = make_area("patio_area", "Outdoor Patio", floor_id="ground_floor")
    area_device = make_area("living_area", "Living Room", floor_id="ground_floor")
    floor = make_floor("ground_floor", "Ground Floor")

    device = make_device("dev_shared", area_id="living_area")
    entry = make_entity_entry("light.patio_spot", area_id="patio_area", device_id="dev_shared")

    result = await run_fetch_entities(
        mock_hass,
        entities=[entry],
        devices=[device],
        areas=[area_entity, area_device],
        floors=[floor],
    )
    assert result[0]["area"] == "Outdoor Patio"


@pytest.mark.anyio
async def test_area_and_floor_defaults_to_tba(mock_hass):
    """Verify entities without area or device area default to 'TBA' for both area and floor."""
    entry = make_entity_entry("light.unassigned", area_id=None, device_id=None)

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert result[0]["area"] == "TBA"
    assert result[0]["floor"] == "TBA"


@pytest.mark.anyio
async def test_area_without_floor_defaults_floor_to_tba(mock_hass):
    """Verify area with floor_id=None results in resolved area name and floor='TBA'."""
    area = make_area("porch_area", "Front Porch", floor_id=None)
    entry = make_entity_entry("light.porch_light", area_id="porch_area")

    result = await run_fetch_entities(mock_hass, entities=[entry], areas=[area])
    assert result[0]["area"] == "Front Porch"
    assert result[0]["floor"] == "TBA"


@pytest.mark.anyio
async def test_unregistered_area_or_floor_id_defaults_to_tba(mock_hass):
    """Verify unknown area_id or unknown floor_id defaults safely to 'TBA'."""
    # Area ID not in registry
    entry_bad_area = make_entity_entry("light.bad_area", area_id="nonexistent_area")

    # Area has floor_id that is not in floor registry
    area_bad_floor = make_area("attic_area", "Attic", floor_id="nonexistent_floor")
    entry_bad_floor = make_entity_entry("light.attic_light", area_id="attic_area")

    result = await run_fetch_entities(
        mock_hass,
        entities=[entry_bad_area, entry_bad_floor],
        areas=[area_bad_floor],
        floors=[],
    )
    res_map = {e["entity_id"]: e for e in result}

    assert res_map["light.bad_area"]["area"] == "TBA"
    assert res_map["light.bad_area"]["floor"] == "TBA"

    assert res_map["light.attic_light"]["area"] == "Attic"
    assert res_map["light.attic_light"]["floor"] == "TBA"


# ===========================================================================
# 8. Options, YAML Exposure, Aliases, and Availability
# ===========================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    ("options", "expected_should_expose"),
    [
        ({"conversation": {"should_expose": True}}, True),
        ({"conversation": {"should_expose": False}}, False),
        ({"conversation": {}}, False),
        ({}, False),
        (None, False),
    ],
)
async def test_should_expose_option_resolution(mock_hass, options, expected_should_expose):
    """Verify should_expose resolves correctly from options['conversation']['should_expose']."""
    entry = make_entity_entry("light.expose_test", options=options)

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert result[0]["should_expose"] is expected_should_expose


@pytest.mark.anyio
async def test_yaml_exposed_flag_resolution(mock_hass):
    """Verify yaml_exposed is True only for entities present in the loaded YAML mapping."""
    yaml_exposed = {
        "light.in_yaml": {"name": "In YAML Light"},
        "switch.in_yaml": {"name": "In YAML Switch"},
    }

    e1 = make_entity_entry("light.in_yaml")
    e2 = make_entity_entry("light.not_in_yaml")

    result = await run_fetch_entities(
        mock_hass,
        entities=[e1, e2],
        yaml_exposed=yaml_exposed,
    )
    res_map = {e["entity_id"]: e for e in result}

    assert res_map["light.in_yaml"]["yaml_exposed"] is True
    assert res_map["light.not_in_yaml"]["yaml_exposed"] is False


@pytest.mark.anyio
async def test_aliases_sanitization_and_filtering(mock_hass):
    """Verify aliases are sanitized to exclude None, 0, '0', non-strings, and COMPUTED_NAME objects."""
    computed_name_obj = MockComputedNameType()

    raw_aliases = [
        "valid_alias_1",
        "0",
        0,
        "",
        None,
        123,
        computed_name_obj,
        "valid_alias_2",
    ]
    entry = make_entity_entry("light.alias_test", aliases=raw_aliases)

    result = await run_fetch_entities(mock_hass, entities=[entry])
    assert result[0]["aliases"] == ["valid_alias_1", "valid_alias_2"]


@pytest.mark.anyio
async def test_aliases_none_or_empty_returns_empty_list(mock_hass):
    """Verify None or empty aliases gracefully resolve to empty list."""
    e_none = make_entity_entry("light.alias_none", aliases=None)
    e_empty = make_entity_entry("light.alias_empty", aliases=[])

    result = await run_fetch_entities(mock_hass, entities=[e_none, e_empty])
    res_map = {e["entity_id"]: e for e in result}

    assert res_map["light.alias_none"]["aliases"] == []
    assert res_map["light.alias_empty"]["aliases"] == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("state_val", "expected_unavailable"),
    [
        ("on", False),
        ("off", False),
        ("21.5", False),
        ("open", False),
        ("closed", False),
        ("idle", False),
        ("unavailable", True),
        ("unknown", True),
        (None, True),  # Entity absent from hass.states
    ],
)
async def test_state_availability_resolution(mock_hass, state_val, expected_unavailable):
    """Verify entity unavailable boolean correctly flags unavailable, unknown, or missing states."""
    eid = "light.state_test"
    entry = make_entity_entry(eid)

    states = {}
    if state_val is not None:
        states[eid] = make_state(eid, state=state_val)

    result = await run_fetch_entities(mock_hass, entities=[entry], states=states)
    assert result[0]["unavailable"] is expected_unavailable


# ===========================================================================
# 9. Full Payload Schema and Combined Integration Verification
# ===========================================================================

@pytest.mark.anyio
async def test_full_entity_payload_structure(mock_hass):
    """Verify that every entity in the returned list matches the required 14-field schema."""
    area = make_area("living_room", "Living Room", floor_id="ground")
    floor = make_floor("ground", "Ground Floor")
    device = make_device("dev_hue", name_by_user="Hue Chandelier", area_id="living_room")

    entry = make_entity_entry(
        "light.living_room_ceiling",
        name="Ceiling Light",
        original_name="Hue Lamp",
        device_id="dev_hue",
        area_id="living_room",
        device_class=None,
        original_device_class=None,
        aliases=["overhead light", "ceiling lamp"],
        options={"conversation": {"should_expose": True}},
        platform="hue",
    )

    state = make_state("light.living_room_ceiling", state="on")
    group_state = make_state(
        "light.living_room_group",
        attributes={"entity_ids": ["light.living_room_ceiling"]},
    )
    yaml_exposed = {"light.living_room_ceiling": {}}

    result = await run_fetch_entities(
        mock_hass,
        entities=[entry],
        devices=[device],
        areas=[area],
        floors=[floor],
        yaml_exposed=yaml_exposed,
        states={"light.living_room_ceiling": state},
        light_states=[group_state],
    )

    assert len(result) == 1
    ent = result[0]

    # Verify all 14 expected keys exist
    expected_keys = {
        "entity_id",
        "name",
        "original_name",
        "display_name",
        "device_class",
        "platform",
        "should_expose",
        "yaml_exposed",
        "area",
        "floor",
        "domain",
        "aliases",
        "in_group",
        "unavailable",
    }
    assert set(ent.keys()) == expected_keys

    # Verify exact values
    assert ent["entity_id"] == "light.living_room_ceiling"
    assert ent["name"] == "Ceiling Light"
    assert ent["original_name"] == "Hue Lamp"
    assert ent["display_name"] == "Ceiling Light"
    assert ent["device_class"] == ""
    assert ent["platform"] == "hue"
    assert ent["should_expose"] is True
    assert ent["yaml_exposed"] is True
    assert ent["area"] == "Living Room"
    assert ent["floor"] == "Ground Floor"
    assert ent["domain"] == "light"
    assert ent["aliases"] == ["overhead light", "ceiling lamp"]
    assert ent["in_group"] is True
    assert ent["unavailable"] is False
