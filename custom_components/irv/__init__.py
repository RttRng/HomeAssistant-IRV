from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .mqtt_handler import IRVMQTTHandler

DOMAIN = "irv"

PLATFORMS = ["sensor", "binary_sensor", "switch", "button", "select"]


async def async_setup(hass: HomeAssistant, config: ConfigType):
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # 1) vytvořit handler
    handler = IRVMQTTHandler(hass)

    # 2) uložit handler do hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["handler"] = handler

    # 3) spustit platformy (vytvoří entity)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 4) subscribe na MQTT (až po vytvoření entit)
    await handler.async_subscribe()

    # 5) obnovit stavy (až po subscribe)
    await handler.restore_outputs()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop("handler", None)
    return unload_ok