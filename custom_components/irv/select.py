from homeassistant.components.select import SelectEntity

DOMAIN = "irv"

# -----------------------------
# SG READY SELECT
# -----------------------------

SG_READY_MAP = {
    "0:0": "0:0 - Normální běh",
    "1:0": "1:0 - Blokace běhu",
    "0:1": "0:1 - 120% (Vlastní 1)",
    "1:1": "1:1 - 150% (Vlastní 2)",
}

class IRVSGReadySelect(SelectEntity):
    """SG Ready mode selector (desired state)."""

    def __init__(self, handler):
        self.handler = handler

        # dva MQTT topicy, ale používáme je jen při změně uživatelem
        self._mqtt_topics = [
            "control/mirosov/rele1",
            "control/mirosov/rele2",
        ]

        self._attr_name = "SG Ready režim"
        self._attr_unique_id = "irv_sg_ready_select"
        self.entity_id = "select.irv_sg_ready"

        self._attr_options = list(SG_READY_MAP.values())
        self._state = SG_READY_MAP["0:0"]

        self._restored = False

    @property
    def current_option(self):
        return self._state

    async def async_select_option(self, option):
        """User selected a new SG Ready mode."""
        self._state = option
        self.async_write_ha_state()

        # uložit stav entity
        await self.handler.publish(
            topic=None,
            payload=self._encode_state(option),
            entity_id=self.entity_id,
        )

        # poslat do Pico
        await self._apply_mode(option)

    async def _apply_mode(self, option):
        """Convert selected option to relay commands."""
        code = option.split(" ")[0]  # "0:0"
        r1, r2 = code.split(":")

        payload1 = "true" if r1 == "1" else "false"
        payload2 = "true" if r2 == "1" else "false"

        await self.handler.publish("control/mirosov/rele1", payload1, retain=True, qos=2)
        await self.handler.publish("control/mirosov/rele2", payload2, retain=True, qos=2)

    def update_from_relays(self, r1, r2):
        """Update select state based on actual relay feedback."""
        if self._restored:
            return  # po startu ignorujeme MQTT

        code = f"{1 if r1 else 0}:{1 if r2 else 0}"
        self._state = SG_READY_MAP[code]
        self.async_write_ha_state()

    def set_restored_state(self, payload):
        """Restore UI state after restart without sending MQTT."""
        self._restored = True

        # payload je např. "0:1"
        if payload in SG_READY_MAP:
            self._state = SG_READY_MAP[payload]
            if self.hass:
                self.async_write_ha_state()

    def _encode_state(self, option):
        """Convert full label back to '0:1' form."""
        return option.split(" ")[0]



# -----------------------------
# SETUP ENTRY
# -----------------------------
async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data["irv"]["handler"]

    sg_select = IRVSGReadySelect(handler)
    handler.register_switch(None, None, sg_select)

    async_add_entities([sg_select])
