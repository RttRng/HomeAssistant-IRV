from homeassistant.components.switch import SwitchEntity

DOMAIN = "irv"

# ---------------------------------------------------------
#  A) RELÉ SWITCH – plná obnova + MQTT publish
# ---------------------------------------------------------

class IRVSwitch(SwitchEntity):
    """MQTT control switch for Pico relays."""

    def __init__(self, handler, room, topic, name):
        self.handler = handler
        self.room = room
        self.topic = topic

        # MQTT topic pro Pico
        self._mqtt_topic = f"control/{room}/{topic}"

        # HA metadata
        self._attr_name = f"Pico {room} {name}"
        self._attr_unique_id = f"irv_switch_{room}_{topic}"

        # interní stav
        self._state = False
        self._restored = False

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self, **kwargs):
        self._state = True
        self.async_write_ha_state()

        await self.handler.publish(
            self._mqtt_topic,
            "true",
            retain=True,
            qos=2,
            entity_id=self.entity_id,
        )

    async def async_turn_off(self, **kwargs):
        self._state = False
        self.async_write_ha_state()

        await self.handler.publish(
            self._mqtt_topic,
            "false",
            retain=True,
            qos=2,
            entity_id=self.entity_id,
        )

    def update_from_sensor(self, value):
        """MQTT update from Pico — ignorujeme po obnově."""
        if self._restored:
            return
        self._state = value
        self.async_write_ha_state()

    def set_restored_state(self, state):
        """Obnova stavu po restartu HA."""
        self._restored = True
        self._state = (str(state).lower() == "true")
        self.async_write_ha_state()


# ---------------------------------------------------------
#  C) SETUP ENTRY – registrace entit
# ---------------------------------------------------------

async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]
    entities = []

    # --- Relé switche ---
    SWITCH_MAP = {
        "kotel": ["rele"],
        "borek": ["rele"],
        "obyvak": ["rele"],
        "mirosov": ["rele1", "rele2"],
    }

    for room, topics in SWITCH_MAP.items():
        for topic in topics:
            sw = IRVSwitch(handler, room, topic, topic)
            handler.register_switch(room, topic, sw)  # handler si uloží entity_id → entity
            entities.append(sw)

    async_add_entities(entities)
