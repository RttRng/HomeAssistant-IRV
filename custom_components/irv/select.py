"""Select platform for IRV."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import DOMAIN, control_topic
from .peripheral import Peripheral


class IRVSGReadySelect(SelectEntity):
    """Desired-state select for an SGReady peripheral.

    Options are the peripheral's own 4 label strings, published verbatim
    as the MQTT command (matches irv_lib.py's SGReady.command()).
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
        self._state: str | None = None  # unknown until set or restored

    @property
    def current_option(self):
        return self._state

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        saved = self.handler.get_saved_state(self)
        if saved in self._attr_options:  # ignore if labels were renamed
            self._state = saved

    async def async_publish_state(self):
        if self._state is None:
            return
        await self.handler.publish(
            self._mqtt_topic,
            self._state,
            retain=True,
            qos=2,
            state_key=self.unique_id,
        )

    async def async_select_option(self, option: str):
        self._state = option
        self.async_write_ha_state()
        await self.async_publish_state()


class IRVSwitchSelect(SelectEntity):
    """Named-state view of a switch's desired state.

    Holds no state of its own: mirrors the paired IRVSwitch and delegates
    changes to it, so publishing and persistence behave identically.
    """

    def __init__(self, handler, peripheral: Peripheral, device_info, switch):
        self.handler = handler
        self.peripheral = peripheral
        self._switch = switch

        on = peripheral.value_on or "On"
        off = peripheral.value_off or "Off"
        if on == off:
            on, off = "On", "Off"
        self._on_label = on
        self._off_label = off

        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._attr_name = peripheral.name.replace("_", " ").title()
        self._attr_unique_id = f"irv_{peripheral.board}_{peripheral.name}_switch_select"
        self._attr_options = [on, off]

    @property
    def current_option(self):
        if self._switch.is_on is None:
            return None
        return self._on_label if self._switch.is_on else self._off_label

    async def async_select_option(self, option: str):
        if option == self._on_label:
            await self._switch.async_turn_on()
        elif option == self._off_label:
            await self._switch.async_turn_off()


async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]
    handler.add_select_entities = async_add_entities
    async_add_entities([])