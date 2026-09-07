"""Pytest fixtures and environment shims for Google Assistant Entity Console."""

from __future__ import annotations

import datetime
import sys
import types
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web
import pytest

# ---------------------------------------------------------------------------
# Host / CI Shim: minimal Home Assistant mock modules if not installed
# ---------------------------------------------------------------------------
try:
    import homeassistant  # noqa: F401
except ImportError:
    class MockModule(types.ModuleType):
        """Dynamic mock module that returns MagicMock for missing attributes."""

        def __init__(self, name: str) -> None:
            super().__init__(name)
            self.__file__ = f"<mock {name}>"
            self.__path__ = []

        def __getattr__(self, item: str):
            if item.startswith("__") and item.endswith("__"):
                raise AttributeError(item)
            val = MagicMock()
            setattr(self, item, val)
            return val

    def register_mock(name: str, mod: types.ModuleType | None = None) -> types.ModuleType:
        if name in sys.modules:
            return sys.modules[name]
        if mod is None:
            mod = MockModule(name)
        sys.modules[name] = mod
        parts = name.split(".")
        if len(parts) > 1:
            parent_name = ".".join(parts[:-1])
            parent = register_mock(parent_name)
            setattr(parent, parts[-1], mod)
        return mod

    class _HomeAssistantMockLoader:
        def __init__(self, mod: types.ModuleType) -> None:
            self.mod = mod

        def create_module(self, spec):
            return self.mod

        def exec_module(self, module):
            pass

    class _HomeAssistantMockFinder:
        def find_spec(self, fullname: str, path, target=None):
            if fullname == "homeassistant" or fullname.startswith("homeassistant."):
                from importlib.machinery import ModuleSpec

                mod = register_mock(fullname)
                return ModuleSpec(fullname, _HomeAssistantMockLoader(mod))
            return None

    sys.meta_path.insert(0, _HomeAssistantMockFinder())

    # Root module
    ha = register_mock("homeassistant")

    # core
    core = register_mock("homeassistant.core")

    class HomeAssistant:
        pass

    class Context:
        def __init__(self, user_id: str | None = None) -> None:
            self.user_id = user_id

    def callback(func):
        return func

    core.HomeAssistant = HomeAssistant
    core.Context = Context
    core.callback = callback

    # config_entries
    config_entries = register_mock("homeassistant.config_entries")

    class ConfigEntry:
        def __init__(
            self,
            entry_id: str = "test_entry",
            domain: str = "google_assistant_entity_console",
            data: dict | None = None,
            options: dict | None = None,
        ) -> None:
            self.entry_id = entry_id
            self.domain = domain
            self.data = data or {}
            self.options = options or {}

    class ConfigFlow:
        def __init_subclass__(cls, domain: str | None = None, **kwargs) -> None:
            super().__init_subclass__(**kwargs)
            cls._domain = domain

        def _async_current_entries(self):
            return []

        def async_abort(self, reason: str):
            return {"type": "abort", "reason": reason}

        def async_create_entry(self, title: str, data: dict):
            return {"type": "create_entry", "title": title, "data": data}

        def async_show_form(
            self,
            step_id: str,
            user_input: dict | None = None,
            errors: dict | None = None,
            description_placeholders: dict | None = None,
        ):
            return {"type": "form", "step_id": step_id, "errors": errors}

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow

    # components.http
    http = register_mock("homeassistant.components.http")

    class HomeAssistantView:
        url = None
        name = None
        requires_auth = True
        extra_urls = []

        def json(self, result, status_code: int = 200, headers: dict | None = None):
            return web.json_response(result, status=status_code, headers=headers)

    class StaticPathConfig:
        def __init__(self, url_path: str | None = None, path: str | None = None, cache_headers: bool = True) -> None:
            self.url_path = url_path
            self.path = path
            self.cache_headers = cache_headers

    http.HomeAssistantView = HomeAssistantView
    http.StaticPathConfig = StaticPathConfig

    # components.frontend
    frontend = register_mock("homeassistant.components.frontend")
    frontend.async_register_built_in_panel = MagicMock()
    frontend.async_remove_panel = MagicMock()

    # components.conversation
    conversation = register_mock("homeassistant.components.conversation")
    conversation.async_converse = AsyncMock()
    conversation.async_get_agent_info = MagicMock()

    # loader
    loader = register_mock("homeassistant.loader")

    async def async_get_integration(hass, domain):
        integ = MagicMock()
        integ.version = "1.0.3"
        return integ

    loader.async_get_integration = async_get_integration

    # util / util.dt
    util = register_mock("homeassistant.util")
    dt_mod = register_mock("homeassistant.util.dt")
    dt_mod.now = lambda: datetime.datetime.now(datetime.timezone.utc)
    util.dt = dt_mod

    # helpers
    helpers = register_mock("homeassistant.helpers")
    area_reg_mod = register_mock("homeassistant.helpers.area_registry")
    dev_reg_mod = register_mock("homeassistant.helpers.device_registry")
    ent_reg_mod = register_mock("homeassistant.helpers.entity_registry")
    floor_reg_mod = register_mock("homeassistant.helpers.floor_registry")
    aiohttp_client_mod = register_mock("homeassistant.helpers.aiohttp_client")
    aiohttp_client_mod.async_get_clientsession = MagicMock()

    area_reg_mod.async_get = MagicMock(return_value=MagicMock(async_list_areas=MagicMock(return_value=[])))
    dev_reg_mod.async_get = MagicMock(return_value=MagicMock(devices={}))
    ent_reg_mod.async_get = MagicMock(return_value=MagicMock(entities={}))
    floor_reg_mod.async_get = MagicMock(return_value=MagicMock(async_list_floors=MagicMock(return_value=[])))

    helpers.area_registry = area_reg_mod
    helpers.device_registry = dev_reg_mod
    helpers.entity_registry = ent_reg_mod
    helpers.floor_registry = floor_reg_mod
    helpers.aiohttp_client = aiohttp_client_mod


# ---------------------------------------------------------------------------
# Standard Shared Pytest Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_hass():
    """Return a mock HomeAssistant instance with standard attributes."""
    hass = MagicMock()
    hass.config.path.return_value = "dummy_settings.json"
    hass.data = {}
    hass.services.async_call = AsyncMock()
    hass.states.async_all = MagicMock(return_value=[])
    hass.states.get = MagicMock(return_value=None)
    hass.bus.async_fire = MagicMock()
    return hass


@pytest.fixture
def mock_entity_registry():
    """Return a mock entity registry with dict lookup and update methods."""
    reg = MagicMock()
    reg.entities = {}
    reg.async_get = MagicMock(side_effect=lambda entity_id: reg.entities.get(entity_id))
    reg.async_update_entity = MagicMock()
    reg.async_update_entity_options = MagicMock()
    return reg


@pytest.fixture
def mock_device_registry():
    """Return a mock device registry with dict lookup."""
    reg = MagicMock()
    reg.devices = {}
    reg.async_get = MagicMock(side_effect=lambda dev_id: reg.devices.get(dev_id))
    return reg


@pytest.fixture
def mock_area_registry():
    """Return a mock area registry with area listing and lookup."""
    reg = MagicMock()
    reg.areas = {}
    reg.async_list_areas = MagicMock(return_value=[])
    reg.async_get_area = MagicMock(side_effect=lambda area_id: reg.areas.get(area_id))
    return reg


@pytest.fixture
def mock_floor_registry():
    """Return a mock floor registry with floor listing and lookup."""
    reg = MagicMock()
    reg.floors = {}
    reg.async_list_floors = MagicMock(return_value=[])
    reg.async_get_floor = MagicMock(side_effect=lambda floor_id: reg.floors.get(floor_id))
    return reg
