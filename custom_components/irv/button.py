from homeassistant.components.button import ButtonEntity

from .const import BUTTONS, DOMAIN


class IRVButton(ButtonEntity):
    """Static MQTT action button."""

    def __init__(self, handler, name, topic, payload):
        self.handler = handler
        self._attr_name = name
        self._attr_unique_id = f"irv_button_{topic.replace('/', '_')}"
        self.topic = topic
        self.payload = payload

    async def async_press(self):
        await self.handler.publish(self.topic, self.payload, retain=False, qos=1)


class IRVSendAllSwitchesButton(ButtonEntity):
    """Re-sends every control entity's desired state (switches + SGReady)."""

    def __init__(self, handler):
        self.handler = handler
        self._attr_name = "Send All Controls"
        self._attr_unique_id = "irv_button_send_all_switches"  # kept so the entity isn't duplicated

    async def async_press(self):
        await self.handler.send_all_controls()

async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]

    entities = [
        IRVButton(handler, name, topic, payload)
        for name, topic, payload in BUTTONS
    ]
    entities.append(IRVSendAllSwitchesButton(handler))

    async_add_entities(entities)