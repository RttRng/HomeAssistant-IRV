from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .mqtt_handler import IRVMQTTHandler

PLATFORMS = ["sensor", "binary_sensor", "switch", "button", "select"]


async def async_setup(hass: HomeAssistant, config: ConfigType):
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    handler = IRVMQTTHandler(hass)
    await handler.async_load_state()   # must finish before any entity exists

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["handler"] = handler

    handler.set_entry(entry)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await handler.async_subscribe()

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry):
    """Push newly-saved calibration offsets into the live sensor entities.

    No platform reload needed/wanted - the peripheral set was built up
    dynamically from retained MQTT discovery messages, and a reload would
    mean waiting on those to arrive again.
    """
    handler = hass.data.get(DOMAIN, {}).get("handler")
    if handler:
        handler.apply_corrections_from_options(entry.options)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop("handler", None)
    return unload_ok