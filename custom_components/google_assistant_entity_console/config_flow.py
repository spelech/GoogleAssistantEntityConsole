from __future__ import annotations

from collections.abc import Mapping
from typing import Any

try:
    import voluptuous as vol
except ImportError:  # pragma: no cover

    class _MockVol:
        """Fallback schema builder for test environments without voluptuous."""

        def Schema(self, schema: Any) -> Any:
            return schema

        def Optional(self, key: Any, **kwargs: Any) -> Any:
            return key

        def Required(self, key: Any, **kwargs: Any) -> Any:
            return key

    vol = _MockVol()

from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_HIDE_SIDEBAR, DOMAIN, entry_hide_sidebar


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Google Assistant Entity Console."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            if CONF_HIDE_SIDEBAR in user_input:
                return self.async_create_entry(
                    title="Google Sync",
                    data={},
                    options={CONF_HIDE_SIDEBAR: bool(user_input[CONF_HIDE_SIDEBAR])},
                )
            return self.async_create_entry(title="Google Sync", data={})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_HIDE_SIDEBAR, default=False): bool,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Return the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Google Assistant Entity Console."""

    async def async_step_init(self, user_input=None):
        """Manage the integration options."""
        if user_input is not None:
            options = (
                dict(self.config_entry.options)
                if isinstance(getattr(self.config_entry, "options", None), Mapping)
                else {}
            )
            options[CONF_HIDE_SIDEBAR] = bool(user_input.get(CONF_HIDE_SIDEBAR, False))
            return self.async_create_entry(title="", data=options)

        current_hide_sidebar = entry_hide_sidebar(self.config_entry)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_HIDE_SIDEBAR,
                        default=current_hide_sidebar,
                    ): bool,
                }
            ),
        )
