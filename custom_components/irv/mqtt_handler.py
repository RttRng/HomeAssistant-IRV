from homeassistant.components import mqtt
from homeassistant.helpers.storage import Store
import json
import os
import logging

_LOGGER = logging.getLogger(__name__)


class IRVMQTTHandler:
    """Central MQTT router for IRV integration."""

    def __init__(self, hass):
        self.hass = hass
        self.status_entities = {}
        self.env_sensors = {}

        # entity_id -> entity (switch, select, number, ...)
        self.switches = {}

        # Corrections default + async load
        self.corrections = {}
        hass.loop.create_task(self._load_corrections())

        # Persistent storage for user outputs (switches, SG Ready, log override)
        self.store = Store(hass, 1, "irv_state.json")
        self.saved_state = {}
        hass.loop.create_task(self._load_state())

    # -------------------------------------------------------------------------
    # REGISTRACE ENTIT
    # -------------------------------------------------------------------------

    def register_env_sensor(self, room, topic, entity):
        if room not in self.env_sensors:
            self.env_sensors[room] = {}
        self.env_sensors[room][topic] = entity

    def register_status_entity(self, name, entity):
        """Register binary sensors for online/offline status."""
        self.status_entities[name] = entity

    def register_switch(self, room, topic, entity):
        """Register user-controlled entities (for restore + mapping)."""
        # room a topic necháme kvůli kompatibilitě, ale pro obnovu používáme entity_id
        self.switches[entity.entity_id] = entity

    # -------------------------------------------------------------------------
    # PERSISTENCE
    # -------------------------------------------------------------------------

    async def _load_corrections(self):
        path = os.path.join(os.path.dirname(__file__), "corrections.json")
        if not os.path.exists(path):
            self.corrections = {}
            return

        def _load():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        self.corrections = await self.hass.async_add_executor_job(_load)

    async def _load_state(self):
        data = await self.store.async_load()
        if data:
            self.saved_state = data

    async def save_state(self):
        await self.store.async_save(self.saved_state)

    async def publish(self, topic, payload, qos=0, retain=False, entity_id=None):
        # 1) uložit stav entity
        if entity_id is not None:
            self.saved_state[entity_id] = payload
            await self.save_state()

        # 2) pokud není topic → nic neposílat do MQTT
        if not topic:
            return

        # 3) normální MQTT publish
        await mqtt.async_publish(
            self.hass,
            topic,
            payload,
            qos=qos,
            retain=retain,
        )


    async def restore_outputs(self):
        """
        Restore last known UI states after restart.

        - pracujeme s entity_id -> state
        - pro relé (entita má _mqtt_topic) pošleme i MQTT retain na Pico
        """
        if not self.saved_state:
            return


        for entity_id, state in self.saved_state.items():
            entity = self.switches.get(entity_id)
            if not entity:
                continue

            if hasattr(entity, "set_restored_state"):
                try:
                    entity.set_restored_state(state)
                except Exception as e:
                    _LOGGER.warning(e)
            # pokud má entita definovaný MQTT topic, pošleme i retain na Pico
            # topic = getattr(entity, "_mqtt_topic", None)
            # if topic:
            #     await mqtt.async_publish(self.hass, topic, state, retain=True)

    # -------------------------------------------------------------------------
    # MQTT SUBSCRIBE + ROUTING
    # -------------------------------------------------------------------------

    async def async_subscribe(self):
        topics = [
            "status",
            "obyvak",
            "koupelna",
            "borek",
            "kotel",
            "mirosov",
            "test",
            "test/sleep",
            "koupelna/sleep",
            "ping",
        ]

        for t in topics:
            await mqtt.async_subscribe(
                self.hass,
                t,
                self._mqtt_message,
            )


    async def _mqtt_message(self, *args):
        if len(args) == 3:
            topic, payload, qos = args
        else:
            msg = args[0]
            topic = msg.topic
            payload = msg.payload
            qos = msg.qos

        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")

        # JSON batch update (environment data)
        if payload.startswith("{") and payload.endswith("}"):
            try:
                data = json.loads(payload)
            except Exception:
                _LOGGER.warning("IRV: invalid JSON on topic %s: %s", topic, payload)
                return

            room = topic  # topic IS the room name
            await self._handle_env_json(room, data)
            return
        if topic == "ping":
            await self._handle_ping(payload)
            return

        # status messages
        if topic == "status":
            await self._handle_status(payload)
            return

    # -------------------------------------------------------------------------
    # ENVIRONMENT JSON + CORRECTIONS
    # -------------------------------------------------------------------------

    async def _handle_env_json(self, room, data: dict):
        """Handle JSON payload where keys contain full topic paths + apply corrections."""

        room_sensors = self.env_sensors.get(room)
        if not room_sensors:
            return

        # corrections can be structured in two ways:
        # 1) per-room: self.corrections[room][subtopic]
        # 2) global:   self.corrections[full_key]
        room_corr = self.corrections.get(room, {})

        for full_key, raw_value in data.items():
            # NEW FORMAT: keys are already subtopics ("in", "out", "rele", ...)
            subtopic = full_key

            sensor = room_sensors.get(subtopic)
            if not sensor:
                continue

            # parse číslo, pokud to jde
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                value = raw_value

            # 1) per-room corrections: corrections[room][subtopic]
            corr = room_corr.get(subtopic)

            # 2) global corrections: corrections["koupelna/bme/teplota"]
            if corr is None:
                corr = self.corrections.get(full_key)

            # aplikace korekcí – očekáváme např.:
            # { "koupelna": { "bme/teplota": { "offset": -0.8 } } }
            # nebo { "koupelna/bme/teplota": { "offset": -0.8, "factor": 1.0 } }
            if isinstance(value, (int, float)) and isinstance(corr, dict):
                offset = corr.get("offset", 0)
                factor = corr.get("factor", 1)
                value = value * factor + offset
            sensor.update_value(value)

            if room == 'mirosov':
                self.sg_ready_sensor.update_from_relays()

    # -------------------------------------------------------------------------
    # STATUS + LOG
    # -------------------------------------------------------------------------

    async def _handle_status(self, payload):
        if payload == "goodbye":
            for ent in self.status_entities.values():
                ent.set_offline()
            return

        ent = self.status_entities.get(payload)
        if ent:
            ent.set_online()

    async def _handle_ping(self,payload):
        await self.publish(
            "pong",
            payload,
            retain=False,
            qos=2,
            entity_id=None,
        )