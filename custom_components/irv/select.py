"""Select platform for IRV (desired state for SGREADY peripherals)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import DOMAIN, control_topic
from .peripheral import Peripheral


class IRVSGReadySelect(SelectEntity):
    """Desired-state select for an SGReady peripheral.

    Options are the peripheral's own 4 label strings (value00/01/10/11), as
    declared in its board's discovery payload. The selected label is
    published verbatim as the MQTT command, matching irv_lib.py's
    SGReady.command().
    """

    def __init__(self, handler, peripheral: Peripheral, device_info):
        self.handler = handler
        self.peripheral = peripheral
        self._mqtt_topic = control_topic(peripheral.board, peripheral.name)

        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._attr_name = peripheral.name.replace("_", " ").title()
        self._attr_unique_id = f"irv_{peripheral.board}_{peripheral.name}_select"

        self._attr_options = [
            opt
            for opt in (
                peripheral.value00,
                peripheral.value01,
                peripheral.value10,
                peripheral.value11,
            )
            if opt is not None
        ]
        self._state = peripheral.value00
        self._restored = False

    @property
    def current_option(self):
        return self._state

    async def async_select_option(self, option: str):
        self._state = option
        self.async_write_ha_state()

        await self.handler.publish(
            self._mqtt_topic, option, retain=True, qos=2, entity_id=self.entity_id
        )

    def set_restored_state(self, state):
        """Restore UI state after an HA restart, without publishing to MQTT."""
        self._restored = True
        if state in self._attr_options:
            self._state = state
            if self.hass:
                self.async_write_ha_state()


async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]
    handler.add_select_entities = async_add_entities
    async_add_entities([])
