"""Sensor platform for IRV.

Three entity classes cover everything:
- IRVSensor: numeric/plain-value sensors (DHT, BME sub-sensors, version/in/out).
- IRVLabelSensor: text sensor showing the human-readable label of a
  RELE/VENTIL/SGREADY peripheral's actual (reported) state.
- IRVIntegrationVersionSensor: static sensor showing the installed
  integration's own manifest.json version (not a board's firmware version).
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .peripheral import Peripheral


def _friendly(name: str) -> str:
    return name.replace("/", " ").replace("_", " ").title()


class IRVSensor(SensorEntity):
    """Numeric/plain sensor fed from an IRV state report.

    Keeps the last raw (as-reported) value separately from the displayed
    value so a calibration offset changed later in the HA UI (see
    IRVMQTTHandler.apply_corrections_from_options) can be re-applied
    immediately, without waiting for the next MQTT report.
    """

    def __init__(self, handler, peripheral: Peripheral, device_info):
        self.handler = handler
        self.peripheral = peripheral

        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._attr_name = _friendly(peripheral.name)
        self._attr_unique_id = f"irv_{peripheral.board}_{peripheral.name}_sensor"
        self._attr_native_unit_of_measurement = peripheral.unit

        self._raw_value = None
        self._correction = 0.0
        self._state = None

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        if self._correction:
            return {"raw_value": self._raw_value, "correction_offset": self._correction}
        return None

    def update_value(self, value, unit=None):
        if self.hass is None:
            return

        if unit is not None and unit != self._attr_native_unit_of_measurement:
            self._attr_native_unit_of_measurement = unit

        try:
            value = float(value)
        except (TypeError, ValueError):
            pass

        self._raw_value = value
        self._recompute_and_write()

    def set_correction(self, offset: float):
        """Apply a new calibration offset (from the HA options-flow UI)
        immediately, without needing a fresh MQTT report to land first.
        """
        self._correction = offset or 0.0
        if self.hass is not None and self._raw_value is not None:
            self._recompute_and_write()

    def _recompute_and_write(self):
        value = self._raw_value
        if isinstance(value, (int, float)) and self._correction:
            value = value + self._correction
        self._state = value
        self.async_write_ha_state()


class IRVRawStateSensor(SensorEntity):
    """Raw 'X:Y' state string for SGReady, meant for use in automations.

    Kept separate from IRVLabelSensor (which shows the human label) so
    automations have a stable, hardcoded-format value to match against
    regardless of what labels get renamed to later.
    """

    def __init__(self, handler, peripheral: Peripheral, device_info):
        self.handler = handler
        self.peripheral = peripheral

        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._attr_name = f"{_friendly(peripheral.name)} Raw State"
        self._attr_unique_id = f"irv_{peripheral.board}_{peripheral.name}_raw"

        self._state = None

    @property
    def native_value(self):
        return self._state

    def update_value(self, raw_state):
        if self.hass is None:
            return
        self._state = raw_state
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


class IRVIntegrationVersionSensor(SensorEntity):
    """Static sensor showing the installed IRV integration's own version.

    Read straight from manifest.json via async_get_integration rather than
    hardcoded a second time anywhere, so it can't drift out of sync with
    what's actually installed. Deliberately separate from any Pico board's
    device - this is the HA-side integration version, not firmware version.
    """

    _attr_has_entity_name = True
    _attr_name = "Integration Version"
    _attr_unique_id = "irv_integration_version"
    _attr_entity_category = "diagnostic"

    def __init__(self, version: str):
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "integration")},
            name="IRV Integration",
            manufacturer="RttRng",
            model="Home Assistant Integration",
        )
        self._state = version

    @property
    def native_value(self):
        return self._state


async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]
    handler.add_sensor_entities = async_add_entities

    integration = await async_get_integration(hass, DOMAIN)
    version = integration.manifest.get("version", "unknown")
    async_add_entities([IRVIntegrationVersionSensor(version)])

    # No board-derived entities exist yet - they arrive asynchronously as
    # boards announce themselves on 'discovery/<board>' (retained, so
    # typically within seconds of MQTT connecting, but the integration
    # tolerates it taking up to the board's own retained-message lifetime
    # after HA boot).