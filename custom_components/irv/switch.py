"""Switch platform for IRV (desired state for RELE / VENTIL peripherals)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN, control_topic
from .peripheral import Peripheral


class IRVSwitch(SwitchEntity):
    """Desired-state switch. Publishes plain 'true'/'false' to control/<board>/<name>."""

    def __init__(self, handler, peripheral: Peripheral, device_info):
        self.handler = handler
        self.peripheral = peripheral
        self._mqtt_topic = control_topic(peripheral.board, peripheral.name)

        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._attr_name = peripheral.name.replace("_", " ").title()
        self._attr_unique_id = f"irv_{peripheral.board}_{peripheral.name}_switch"

        self._state = False
        self._restored = False

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self, **kwargs):
        self._state = True
        self.async_write_ha_state()
        await self.handler.publish(
            self._mqtt_topic, "true", retain=True, qos=2, entity_id=self.entity_id
        )

    async def async_turn_off(self, **kwargs):
        self._state = False
        self.async_write_ha_state()
        await self.handler.publish(
            self._mqtt_topic, "false", retain=True, qos=2, entity_id=self.entity_id
        )

    def set_restored_state(self, state):
        """Restore UI state after an HA restart, without publishing to MQTT."""
        self._restored = True
        self._state = str(state).lower() == "true"
        self.async_write_ha_state()


async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]
    handler.add_switch_entities = async_add_entities
    async_add_entities([])
