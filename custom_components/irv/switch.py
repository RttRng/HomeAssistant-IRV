"""Switch platform for IRV (desired state for SWITCH peripherals)."""
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

        # None = desired state not known yet (never set, nothing saved)
        self._state: bool | None = None

    @property
    def is_on(self):
        return self._state

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        saved = self.handler.get_saved_state(self)
        if saved is not None:
            # UI only: the retained MQTT message already tells the board.
            self._state = str(saved).lower() == "true"

    def _sync_select(self):
        ents = self.handler.entities.get(self.peripheral.key, {})
        sel = ents.get("switch_select")
        if sel is not None and sel.hass is not None:
            sel.async_write_ha_state()

    async def async_publish_state(self):
        """Publish the desired state (same settings as on change)."""
        if self._state is None:
            return
        await self.handler.publish(
            self._mqtt_topic,
            "true" if self._state else "false",
            retain=True,
            qos=2,
            state_key=self.unique_id,
        )

    async def async_turn_on(self, **kwargs):
        self._state = True
        self.async_write_ha_state()
        self._sync_select()
        await self.async_publish_state()

    async def async_turn_off(self, **kwargs):
        self._state = False
        self.async_write_ha_state()
        self._sync_select()
        await self.async_publish_state()


async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]
    handler.add_switch_entities = async_add_entities
    async_add_entities([])