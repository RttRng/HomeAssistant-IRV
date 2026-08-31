from homeassistant.components.binary_sensor import BinarySensorEntity

# -----------------------------
# ENVIRONMENT SENSORS
# -----------------------------

ENV_SENSOR_MAP = {
    "obyvak": {
        "rele": ("Relé", None, "binary"),
    },

    "koupelna": {
    },

    "borek": {
        "rele": ("Relé", None, "binary"),
    },

    "kotel": {
        "rele": ("Relé", None, "binary"),
        "ventil": ("Ventil", None, "binary"),
    },

    "mirosov": {
        "rele1": ("Relé 1", None, "binary"),
        "rele2": ("Relé 2", None, "binary"),
    },

    "test": {
    },

    "test/sleep":{
        "sleep": ("Sleep",None,"binary"),
    },
    "koupelna/sleep":{
        "sleep": ("Sleep",None,"binary"),
    },
}

async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data["irv"]["handler"]

    entities = []
    for name in ["kotel", "obyvak", "koupelna", "mirosov", "borek"]:
        ent = IRVStatusBinarySensor(name)
        handler.register_status_entity(name, ent)
        entities.append(ent)

    # ENVIRONMENT SENSORS
    for room, sensors in ENV_SENSOR_MAP.items():
        for topic, (name, unit, kind) in sensors.items():
            ent = IRVEnvBinarySensor(handler, room, topic, name)
            handler.register_env_sensor(room, topic, ent)
            entities.append(ent)

    async_add_entities(entities)



    async_add_entities(entities)

class IRVEnvBinarySensor(BinarySensorEntity):
    """Binary sensor for relays and digital inputs."""

    def __init__(self, handler, room, topic, name):
        self.handler = handler
        self.room = room
        self.topic = topic
        self._attr_name = f"Pico {room} {name}"
        self._attr_unique_id = f"irv_env_bin_{room}_{topic}"
        self._state = False
        self._restored = False

    @property
    def is_on(self):
        return self._state

    def update_value(self, value):
        if self.hass is None:
            return
        self._state = bool(value)
        self.async_write_ha_state()


class IRVStatusBinarySensor(BinarySensorEntity):
    """Binary sensor representing online/offline status of a room."""

    def __init__(self, name):
        self._attr_name = f"Pico {name} stav"
        self._attr_unique_id = f"irv_status_{name}"
        self._state = False
        self.room = name

    @property
    def is_on(self):
        return self._state

    def set_online(self):
        self._state = True
        self.async_write_ha_state()

    def set_offline(self):
        self._state = False
        self.async_write_ha_state()
