from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, correction_key


class IRVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Minimal config flow for IRV integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="IRV", data={})

        return self.async_show_form(step_id="user", data_schema=None)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return IRVOptionsFlow(config_entry)


class IRVOptionsFlow(config_entries.OptionsFlow):
    """Per-sensor calibration offset, exposed as the integration's
    Settings -> Devices & Services -> IRV -> Configure form.

    The form's fields are built dynamically from whichever numeric sensors
    the handler has actually seen discovered over MQTT so far, since the
    peripheral set isn't known up front. If no boards have reported in yet,
    the form will be empty - reopen it after boards have announced
    themselves via their retained 'discovery/<board>' topic.
    """

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        handler = self.hass.data.get(DOMAIN, {}).get("handler")
        peripherals = handler.correctable_peripherals() if handler else []

        if not peripherals:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "info": "No numeric sensors discovered yet. Reopen this "
                    "after your boards have reported in over MQTT."
                },
            )

        existing = dict(self.config_entry.options.get("corrections", {}) or {})

        if user_input is not None:
            corrections = {
                correction_key(p.board, p.name): float(user_input.get(correction_key(p.board, p.name), 0.0) or 0.0)
                for p in peripherals
            }
            # Preserve offsets for sensors not currently listed (e.g.
            # briefly offline board), rather than silently dropping them.
            merged = {**existing, **corrections}
            return self.async_create_entry(title="", data={"corrections": merged})

        # Field name is the flattened "board|name" key itself (so
        # async_step_init can read it straight back out of user_input);
        # translations/strings.json maps these to friendly labels in the UI.
        schema_fields = {
            vol.Optional(
                correction_key(p.board, p.name),
                default=existing.get(correction_key(p.board, p.name), 0.0),
            ): vol.Coerce(float)
            for p in sorted(peripherals, key=lambda p: (p.board, p.name))
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema_fields))