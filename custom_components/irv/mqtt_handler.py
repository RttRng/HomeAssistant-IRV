"""Central MQTT router for the IRV integration.

Boards announce themselves on retained 'discovery/<board>' topics. On first
sight of a board we create a Device for it plus all its entities; on later
sight (e.g. firmware redeploy changing the peripheral set) we only add
entities for peripherals we haven't seen before - nothing is ever removed,
so entity history is never lost even if a peripheral disappears.
"""
from __future__ import annotations

import json
import logging
import re

from homeassistant.components import mqtt
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    TOPIC_DISCOVERY_WILDCARD,
    TOPIC_PING,
    TOPIC_PONG,
    TOPIC_STATUS,
    TYPE_SWITCH,
    TYPE_SENSOR,
    TYPE_SGREADY,
    TYPE_BINARYSENSOR,
    IMPLICIT_SENSORS,
    board_from_discovery_topic,
    correction_key,
)
from .peripheral import Peripheral, parse_discovery_payload

_LOGGER = logging.getLogger(__name__)


def _decode(payload) -> str:
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    return payload


def _sgready_raw_state(value) -> str:
    """Normalize an SGReady 'value' field into a hardcoded 'X:Y' string.

    The MCU currently sends the pair as a Python tuple-repr string, e.g.
    "(0, 0)". This extracts the two numbers regardless of that formatting
    (also tolerates a future firmware change that sends "0:0" directly).
    """
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return f"{value[0]}:{value[1]}"
    if isinstance(value, str):
        nums = re.findall(r"-?\d+", value)
        if len(nums) >= 2:
            return f"{nums[0]}:{nums[1]}"
        return value
    return str(value)


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")
    return False


class IRVMQTTHandler:
    """Central MQTT router for IRV integration."""

    def __init__(self, hass):
        self.hass = hass

        # board -> DeviceInfo
        self.devices: dict[str, DeviceInfo] = {}

        # board -> {peripheral_name: Peripheral}
        self.peripherals: dict[str, dict[str, Peripheral]] = {}

        # boards we've already subscribed a report-topic listener for
        self.known_boards: set[str] = set()

        # (board, peripheral_name) -> {"sensor"/"binary_sensor"/"label_sensor"/"switch"/"select": entity}
        self.entities: dict[tuple[str, str], dict[str, object]] = {}

        # board -> status binary_sensor entity (online/offline heartbeat)
        self.status_entities: dict[str, object] = {}



        # async_add_entities callbacks, set by each platform's async_setup_entry
        self.add_sensor_entities = None
        self.add_binary_sensor_entities = None
        self.add_switch_entities = None
        self.add_select_entities = None

        # Persistent storage for user-set outputs (switches, selects)
        self.store = Store(hass, 1, "irv_state.json")
        self.saved_state = {}

        # Config-entry options: the entry itself (set once async_setup_entry
        # has it) plus a flattened "board|name" -> offset map kept in sync
        # with entry.options via apply_corrections_from_options().
        self.entry = None
        self.corrections: dict[str, float] = {}

    # -------------------------------------------------------------------
    # NUMERIC SENSOR CORRECTIONS (calibration offsets, HA options-flow UI)
    # -------------------------------------------------------------------

    def correctable_peripherals(self) -> list[Peripheral]:
        """Numeric sensors eligible for a calibration offset.

        Plain sensors, excluding the implicit debug counters
        (version/in/out/crashes/flags) where an offset is meaningless.

        Deliberately does NOT filter on p.unit: DHT peripherals are
        discovered with unit=None (the unit only arrives with each MQTT
        report and is applied to the live entity, never written back onto
        the stored Peripheral), so filtering on unit here would silently
        exclude every DHT sensor.
        """
        result = []
        for board_peripherals in self.peripherals.values():
            for p in board_peripherals.values():
                if p.ptype == TYPE_SENSOR and p.name not in IMPLICIT_SENSORS:
                    result.append(p)
        return result

    def set_entry(self, entry):
        self.entry = entry
        self.apply_corrections_from_options(entry.options)

    def apply_corrections_from_options(self, options: dict):
        """Reload self.corrections from entry.options and push any changed
        offsets straight into the live sensor entities (no reload needed).
        """
        new_corrections = dict(options.get("corrections", {}) or {})

        changed_keys = {
            key
            for key in set(new_corrections) | set(self.corrections)
            if new_corrections.get(key, 0.0) != self.corrections.get(key, 0.0)
        }

        self.corrections = new_corrections

        for board_peripherals in self.peripherals.values():
            for p in board_peripherals.values():
                key = correction_key(p.board, p.name)
                if key not in changed_keys:
                    continue
                ents = self.entities.get(p.key)
                if not ents:
                    continue
                sensor_ent = ents.get("sensor")
                if sensor_ent and hasattr(sensor_ent, "set_correction"):
                    sensor_ent.set_correction(self.corrections.get(key, 0.0))

    def get_correction(self, board: str, name: str) -> float:
        return self.corrections.get(correction_key(board, name), 0.0)

    # -------------------------------------------------------------------
    # REGISTRATION HELPERS
    # -------------------------------------------------------------------

    def register_status_entity(self, board, entity):
        self.status_entities[board] = entity

    def register_switch(self, entity):
        """Register a desired-state entity (switch or select) for restore-on-boot."""
        self.switches[entity.entity_id] = entity

    def _register_entity(self, peripheral: Peripheral, kind: str, entity):
        self.entities.setdefault(peripheral.key, {})[kind] = entity

    def _device_info(self, board: str) -> DeviceInfo:
        if board not in self.devices:
            self.devices[board] = DeviceInfo(
                identifiers={(DOMAIN, board)},
                name=f"Pico {board}",
                manufacturer="RttRng",
                model="IRV MCU",
            )
        return self.devices[board]

    # -------------------------------------------------------------------
    # PERSISTENCE
    # -------------------------------------------------------------------

    async def async_load_state(self):
        data = await self.store.async_load()
        if data:
            self.saved_state = data

    async def save_state(self):
        await self.store.async_save(self.saved_state)

    def get_saved_state(self, entity):
        """Last desired state for a control entity, or None.

        Keyed by unique_id (stable across renames); falls back to the
        entity_id key used by older versions of this integration.
        """
        return self.saved_state.get(
            entity.unique_id, self.saved_state.get(entity.entity_id)
        )

    async def publish(self, topic, payload, qos=0, retain=False, state_key=None):
        if state_key is not None and self.saved_state.get(state_key) != payload:
            self.saved_state[state_key] = payload
            await self.save_state()

        if not topic:
            return

        await mqtt.async_publish(self.hass, topic, payload, qos=qos, retain=retain)

    async def send_all_controls(self):
        """Re-publish the desired state of every control entity
        (switches and SGReady selects), same qos/retain as on change.
        Entities with no known desired state are skipped.
        """
        for ents in list(self.entities.values()):
            for kind in ("switch", "select"):
                ent = ents.get(kind)
                if ent is None or ent.hass is None:
                    continue
                try:
                    await ent.async_publish_state()
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("IRV: failed to re-send %s", ent.unique_id)

    async def restore_outputs(self):
        """Restore last known desired-state (switch/select) values after restart."""
        if not self.saved_state:
            return

        for entity_id, state in self.saved_state.items():
            entity = self.switches.get(entity_id)
            if not entity:
                continue
            if hasattr(entity, "set_restored_state"):
                try:
                    entity.set_restored_state(state)
                except Exception as e:  # noqa: BLE001
                    _LOGGER.warning(e)

    async def send_all_switches(self):
        """Re-publish the desired state of every switch (retain/qos as on change)."""
        for ents in self.entities.values():
            sw = ents.get("switch")
            if sw is not None and sw.hass is not None:
                await sw.async_publish_state()

    # -------------------------------------------------------------------
    # SUBSCRIBE + ROUTING
    # -------------------------------------------------------------------

    async def async_subscribe(self):
        await mqtt.async_subscribe(self.hass, TOPIC_DISCOVERY_WILDCARD, self._on_discovery_message)
        await mqtt.async_subscribe(self.hass, TOPIC_STATUS, self._on_status_message)
        await mqtt.async_subscribe(self.hass, TOPIC_PING, self._on_ping_message)

    async def _on_discovery_message(self, msg):
        topic = msg.topic
        payload = _decode(msg.payload)

        board = board_from_discovery_topic(topic)
        if not board:
            return

        await self._handle_discovery(board, payload)

    async def _on_status_message(self, msg):
        await self._handle_status(_decode(msg.payload))

    async def _on_ping_message(self, msg):
        await self._handle_ping(_decode(msg.payload))

    def _make_report_callback(self, board: str):
        async def _cb(msg):
            await self._handle_report(board, _decode(msg.payload))

        return _cb

    # -------------------------------------------------------------------
    # JSON HELPERS
    # -------------------------------------------------------------------

    @staticmethod
    def _decode_json_object(payload: str, context: str) -> dict | None:
        """Decode `payload` as JSON and require it to be an object (dict).

        Returns None (and logs a warning) if the payload isn't valid JSON,
        or if it decodes to something other than a JSON object (e.g. a
        bare number, string, list, or null) - both of which are things a
        misbehaving/malicious MQTT publisher can trivially send and which
        previously caused an uncaught AttributeError downstream.
        """
        try:
            data = json.loads(payload)
        except Exception:
            _LOGGER.warning("IRV: invalid JSON on %s: %s", context, payload)
            return None

        if not isinstance(data, dict):
            _LOGGER.warning(
                "IRV: expected a JSON object on %s, got %s: %s",
                context,
                type(data).__name__,
                payload,
            )
            return None

        return data

    # -------------------------------------------------------------------
    # DISCOVERY HANDLING
    # -------------------------------------------------------------------

    async def _handle_discovery(self, board: str, payload: str):
        data = self._decode_json_object(payload, f"'discovery/{board}'")
        if data is None:
            return

        peripherals = parse_discovery_payload(board, data)

        is_new_board = board not in self.known_boards
        if is_new_board:
            self.known_boards.add(board)
            await mqtt.async_subscribe(self.hass, board, self._make_report_callback(board))

        known = self.peripherals.setdefault(board, {})
        new_peripherals = [p for p in peripherals if p.name not in known]
        for p in peripherals:
            known[p.name] = p

        device_info = self._device_info(board)

        if is_new_board:
            self._create_status_entity(board, device_info)

        if new_peripherals:
            self._create_entities_for(board, new_peripherals, device_info)

    def _create_status_entity(self, board: str, device_info: DeviceInfo):
        if not self.add_binary_sensor_entities:
            return

        # Local import to avoid a circular import at module load time.
        from .binary_sensor import IRVStatusBinarySensor

        ent = IRVStatusBinarySensor(board, device_info)
        self.register_status_entity(board, ent)
        self.add_binary_sensor_entities([ent])

    def _create_entities_for(self, board: str, peripherals: list[Peripheral], device_info: DeviceInfo):
        from .sensor import IRVSensor, IRVLabelSensor, IRVRawStateSensor
        from .binary_sensor import IRVBinarySensor
        from .switch import IRVSwitch
        from .select import IRVSGReadySelect, IRVSwitchSelect
        sensors = []
        binaries = []
        switches = []
        selects = []

        for p in peripherals:
            if p.ptype == TYPE_SENSOR:
                ent = IRVSensor(self, p, device_info)
                ent.set_correction(self.get_correction(p.board, p.name))
                self._register_entity(p, "sensor", ent)
                sensors.append(ent)

            elif p.ptype == TYPE_SWITCH:
                sw = IRVSwitch(self, p, device_info)
                self._register_entity(p, "switch", sw)
                switches.append(sw)

                sw_select = IRVSwitchSelect(self, p, device_info, sw)
                self._register_entity(p, "switch_select", sw_select)
                selects.append(sw_select)

                bin_ent = IRVBinarySensor(self, p, device_info)
                self._register_entity(p, "binary_sensor", bin_ent)
                binaries.append(bin_ent)

                label_ent = IRVLabelSensor(self, p, device_info)
                self._register_entity(p, "label_sensor", label_ent)
                sensors.append(label_ent)

            elif p.ptype == TYPE_BINARYSENSOR:
                # Read-only: no control entities.
                bin_ent = IRVBinarySensor(self, p, device_info)
                self._register_entity(p, "binary_sensor", bin_ent)
                binaries.append(bin_ent)

                label_ent = IRVLabelSensor(self, p, device_info)
                self._register_entity(p, "label_sensor", label_ent)
                sensors.append(label_ent)

            elif p.ptype == TYPE_SGREADY:
                sel = IRVSGReadySelect(self, p, device_info)
                self._register_entity(p, "select", sel)
                selects.append(sel)

                label_ent = IRVLabelSensor(self, p, device_info)
                self._register_entity(p, "label_sensor", label_ent)
                sensors.append(label_ent)

                raw_ent = IRVRawStateSensor(self, p, device_info)
                self._register_entity(p, "raw_sensor", raw_ent)
                sensors.append(raw_ent)

            else:
                _LOGGER.warning("IRV: no entity mapping for peripheral type '%s' (%s/%s)", p.ptype, board, p.name)

        if sensors and self.add_sensor_entities:
            self.add_sensor_entities(sensors)
        if binaries and self.add_binary_sensor_entities:
            self.add_binary_sensor_entities(binaries)
        if switches and self.add_switch_entities:
            self.add_switch_entities(switches)
        if selects and self.add_select_entities:
            self.add_select_entities(selects)

    # -------------------------------------------------------------------
    # STATE REPORT HANDLING
    # -------------------------------------------------------------------

    async def _handle_report(self, board: str, payload: str):
        data = self._decode_json_object(payload, f"'{board}'")
        if data is None:
            return

        for name, entry in data.items():
            if not isinstance(entry, dict):
                continue

            ents = self.entities.get((board, name))
            if not ents:
                continue

            value = entry.get("value")
            unit = entry.get("unit")
            label = entry.get("label")

            if label is not None:
                bin_ent = ents.get("binary_sensor")
                if bin_ent:
                    bin_ent.update_value(_parse_bool(value))

                label_ent = ents.get("label_sensor")
                if label_ent:
                    label_ent.update_value(label)

                raw_ent = ents.get("raw_sensor")
                if raw_ent:
                    raw_ent.update_value(_sgready_raw_state(value))
            else:
                sensor_ent = ents.get("sensor")
                if sensor_ent:
                    sensor_ent.update_value(value, unit)

    # -------------------------------------------------------------------
    # STATUS (heartbeat) + PING
    # -------------------------------------------------------------------

    async def _handle_status(self, payload: str):
        if payload == "goodbye":
            for ent in self.status_entities.values():
                ent.set_offline()
            return

        ent = self.status_entities.get(payload)
        if ent:
            ent.set_online()

    async def _handle_ping(self, payload: str):
        await self.publish(TOPIC_PONG+payload, payload, retain=False, qos=2)