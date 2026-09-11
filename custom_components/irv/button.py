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


async def async_setup_entry(hass, entry, async_add_entities):
    handler = hass.data[DOMAIN]["handler"]

    entities = [
        IRVButton(handler, name, topic, payload)
        for name, topic, payload in BUTTONS
    ]

    async_add_entities(entities)
