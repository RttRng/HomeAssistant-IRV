"""Binary sensor platform for IRV."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN
from .peripheral import Peripheral


class IRVBinarySensor(BinarySensorEntity):
    """Actual on/off state of a RELE/VENTIL peripheral, fed from MQTT reports."""

    def __init__(self, handler, peripheral: Peripheral, device_info):
        self.handler = handler
        self.peripheral = peripheral

        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._attr_name = peripheral.name.replace("_", " ").title()
        self._attr_unique_id = f"irv_{peripheral.board}_{peripheral.name}_state"

        self._state = False

    @property
    def is_on(self):
        return self._state

    def update_value(self, value):
        if self.hass is None:
            return
        self._state = bool(value)
        self.async_write_ha_state()


class IRVStatusBinarySensor(BinarySensorEntity):
    """Online/offline heartbeat status for a board (check/goodbye)."""

    def __init__(self, board: str, device_info):
        self.board = board

        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._attr_name = "Status"
        self._attr_unique_id = f"irv_{board}_status"

        self._state = False

    @property
    def is_on(self):
        return self._state

    def set_online(self):
        self._state = True
        self.async_write_ha_state()

    def set_offline(self):
        self._state = False
        self.async_write_ha_state()


async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]
    handler.add_binary_sensor_entities = async_add_entities
    async_add_entities([])
