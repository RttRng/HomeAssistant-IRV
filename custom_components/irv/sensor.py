from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity

# -----------------------------
# ENVIRONMENT SENSORS
# -----------------------------

ENV_SENSOR_MAP = {
    "obyvak": {
        "sonda": ("Sonda", "°C", "sensor"),
        "version": ("Verze",None, "sensor"),
        "in": ("Příchozí","msgs","sensor"),
        "out":("Odchozí","msgs","sensor"),
    },

    "koupelna": {
        "bme/teplota": ("Teplota", "°C", "sensor"),
        "bme/vlhkost": ("Vlhkost", "%", "sensor"),
        "bme/tlak": ("Tlak", "kPa", "sensor"),
        "bme/rosny_bod": ("Rosný bod", "°C", "sensor"),
        "version": ("Verze",None, "sensor"),
        "in": ("Příchozí","msgs","sensor"),
        "out":("Odchozí","msgs","sensor"),
    },

    "borek": {
        "version": ("Verze",None, "sensor"),
        "in": ("Příchozí","msgs","sensor"),
        "out":("Odchozí","msgs","sensor"),
    },

    "kotel": {
        "sonda1": ("Sonda 1", "°C", "sensor"),
        "sonda2": ("Sonda 2", "°C", "sensor"),
        "sonda3": ("Sonda 3", "°C", "sensor"),
        "version": ("Verze",None, "sensor"),
        "in": ("Příchozí","msgs","sensor"),
        "out":("Odchozí","msgs","sensor"),
    },

    "mirosov": {
        "version": ("Verze",None, "sensor"),
        "in": ("Příchozí","msgs","sensor"),
        "out":("Odchozí","msgs","sensor"),
    },

    "test": {
        "version": ("Verze",None, "sensor"),
        "in": ("Příchozí","msgs","sensor"),
        "out":("Odchozí","msgs","sensor"),
    },

    "test/sleep":{
    },
    "koupelna/sleep":{
    },
}


class IRVEnvSensor(SensorEntity):
    """Environment sensor with offset, multiplier and rounding."""

    def __init__(self, handler, room, topic, name, unit):
        self.handler = handler
        self.room = room
        self.topic = topic
        self._attr_name = f"Pico {room} {name}"
        self._attr_unique_id = f"irv_env_{room}_{topic}"
        self._attr_native_unit_of_measurement = unit
        self._state = None
        self._restored = False

        corr = handler.corrections.get(room, {}).get(topic, {})
        self.offset = corr.get("offset", 0.0)
        self.multiplier = corr.get("multiplier", 1.0)
        self.round_digits = corr.get("round", None)

    @property
    def native_value(self):
        return self._state

    def update_value(self, value):
        if self.hass is None:
            return

        if isinstance(value, (int, float)):
            value = (value + self.offset) * self.multiplier
            if self.round_digits is not None:
                value = round(value, self.round_digits)

        self._state = value
        self.async_write_ha_state()




# -----------------------------
# SG READY SENSOR (REAL STATE)
# -----------------------------

class IRVSGReadySensor(SensorEntity):
    def __init__(self, handler):
        self.handler = handler
        self._attr_name = "SG Ready stav"
        self._attr_unique_id = "irv_sg_ready_state"
        self._state = "Neznámý"
        self.r1 = "binary_sensor.pico_mirosov_rele_1"
        self.r2 = "binary_sensor.pico_mirosov_rele_2"

    @property
    def native_value(self):
        return self._state

    def update_from_relays(self):
        if self.hass is None:
            return
        r1 = self.hass.states.get(self.r1).state in ("on","1","true",True)
        r2 = self.hass.states.get(self.r2).state in ("on","1","true",True)
        

        if not r1 and not r2:
            self._state = "0:0 - Normální běh"
        elif r1 and not r2:
            self._state = "1:0 - Blokace běhu"
        elif not r1 and r2:
            self._state = "0:1 - 120% (Vlastní 1)"
        elif r1 and r2:
            self._state = "1:1 - 150% (Vlastní 2)"
        else:
            self._state = "Chyba"

        self.async_write_ha_state()


# -----------------------------
# SETUP ENTRY
# -----------------------------

async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data["irv"]["handler"]
    entities = []

    # ENVIRONMENT SENSORS
    for room, sensors in ENV_SENSOR_MAP.items():
        for topic, (name, unit, kind) in sensors.items():
            ent = IRVEnvSensor(handler, room, topic, name, unit)
            handler.register_env_sensor(room, topic, ent)
            entities.append(ent)

    # SG READY SENSOR
    sg_sensor = IRVSGReadySensor(handler)
    handler.sg_ready_sensor = sg_sensor
    entities.append(sg_sensor)

    async_add_entities(entities)
