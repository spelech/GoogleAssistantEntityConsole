from collections.abc import Mapping
from typing import Any

DOMAIN = "google_assistant_entity_console"
STORAGE_KEY = "google_assistant_entity_console"
STORAGE_VERSION = 1
DATA_STORE = "store"
DATA_RUNTIME = "runtime"
CONF_HIDE_SIDEBAR = "hide_sidebar"


def entry_hide_sidebar(entry: Any) -> bool:
    """Return True if the config entry hides the Home Assistant sidebar panel."""
    options = getattr(entry, "options", None)
    if isinstance(options, Mapping) and CONF_HIDE_SIDEBAR in options:
        return bool(options[CONF_HIDE_SIDEBAR])
    data = getattr(entry, "data", None)
    if isinstance(data, Mapping):
        return bool(data.get(CONF_HIDE_SIDEBAR, False))
    return False
