"""Sensor platform for IRV.

Two entity classes cover everything:
- IRVSensor: numeric/plain-value sensors (DHT, BME sub-sensors, version/in/out).
- IRVLabelSensor: text sensor showing the human-readable label of a
  RELE/VENTIL/SGREADY peripheral's actual (reported) state.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .peripheral import Peripheral


def _friendly(name: str) -> str:
    return name.replace("/", " ").replace("_", " ").title()


class IRVSensor(SensorEntity):
    """Numeric/plain sensor fed from an IRV state report."""

    def __init__(self, handler, peripheral: Peripheral, device_info):
        self.handler = handler
        self.peripheral = peripheral

        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._attr_name = _friendly(peripheral.name)
        self._attr_unique_id = f"irv_{peripheral.board}_{peripheral.name}_sensor"
        self._attr_native_unit_of_measurement = peripheral.unit

        self._state = None

    @property
    def native_value(self):
        return self._state

    def update_value(self, value, unit=None):
        if self.hass is None:
            return

        if unit is not None and unit != self._attr_native_unit_of_measurement:
            self._attr_native_unit_of_measurement = unit

        try:
            value = float(value)
        except (TypeError, ValueError):
            pass

        self._state = value
        self.async_write_ha_state()


class IRVLabelSensor(SensorEntity):
    """Text sensor showing a binary/SGReady peripheral's actual state as a label."""

    def __init__(self, handler, peripheral: Peripheral, device_info):
        self.handler = handler
        self.peripheral = peripheral

        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._attr_name = f"{_friendly(peripheral.name)} Label"
        self._attr_unique_id = f"irv_{peripheral.board}_{peripheral.name}_label"

        self._state = None

    @property
    def native_value(self):
        return self._state

    def update_value(self, label):
        if self.hass is None:
            return
        self._state = label
        self.async_write_ha_state()


async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]
    handler.add_sensor_entities = async_add_entities
    # No entities exist yet - they arrive asynchronously as boards announce
    # themselves on 'discovery/<board>' (retained, so typically within
    # seconds of MQTT connecting, but the integration tolerates it taking
    # up to the board's own retained-message lifetime after HA boot).
    async_add_entities([])
