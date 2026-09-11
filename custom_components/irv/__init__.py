from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .mqtt_handler import IRVMQTTHandler

PLATFORMS = ["sensor", "binary_sensor", "switch", "button", "select"]


async def async_setup(hass: HomeAssistant, config: ConfigType):
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # 1) create handler
    handler = IRVMQTTHandler(hass)

    # 2) store handler in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["handler"] = handler

    # 3) start platforms (registers each platform's async_add_entities callback)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 4) subscribe to MQTT (discovery/#, status, ping) - after platforms so
    #    add_entities callbacks are ready before any discovery message can arrive
    await handler.async_subscribe()

    # 5) restore desired-state entities (switches/selects) after subscribe
    await handler.restore_outputs()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop("handler", None)
    return unload_ok
