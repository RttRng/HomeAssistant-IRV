"""Constants for the IRV integration."""

DOMAIN = "irv"

# -----------------------------------------------------------------------
# TOPICS
# -----------------------------------------------------------------------

TOPIC_DISCOVERY_WILDCARD = "discovery/#"
TOPIC_DISCOVERY_PREFIX = "discovery/"
TOPIC_STATUS = "status"
TOPIC_PING = "ping"
TOPIC_PONG = "pong/"
TOPIC_CONTROL_PREFIX = "control"


def discovery_topic(board: str) -> str:
    """Return the discovery topic for a board, e.g. 'discovery/kotel'."""
    return f"{TOPIC_DISCOVERY_PREFIX}{board}"


def control_topic(board: str, name: str) -> str:
    """Return the control topic for a peripheral, e.g. 'control/kotel/rele'."""
    return f"{TOPIC_CONTROL_PREFIX}/{board}/{name}"


def board_from_discovery_topic(topic: str) -> str | None:
    """Extract the board name from a 'discovery/<board>' topic."""
    if not topic.startswith(TOPIC_DISCOVERY_PREFIX):
        return None
    board = topic[len(TOPIC_DISCOVERY_PREFIX):]
    return board or None


def correction_key(board: str, name: str) -> str:
    """Flatten a (board, name) pair into the string key used in
    entry.options["corrections"], since JSON/HA storage can't use tuple keys.
    """
    return f"{board}|{name}"


# -----------------------------------------------------------------------
# PERIPHERAL TYPES (as they appear in the discovery payload's TYPE field)
# -----------------------------------------------------------------------

TYPE_SWITCH = "SWITCH"
TYPE_BINARYSENSOR = "BINARYSENSOR"
TYPE_SGREADY = "SGREADY"
TYPE_DHT = "DHT"
TYPE_BME = "BME280"

# Internal type used for anything that is "just a plain sensor"
# (DHT peripherals, expanded BME sub-sensors, and the implicit debug sensors)
TYPE_SENSOR = "SENSOR"

# -----------------------------------------------------------------------
# BME280 expansion: one discovered BME peripheral fans out into 4 sensors
# -----------------------------------------------------------------------

BME_SUBSENSORS = {
    "teplota": "°C",
    "tlak": "kPa",
    "vlhkost": "%",
    "rosny_bod": "°C",
}

# -----------------------------------------------------------------------
# Implicit debug sensors present on every board, regardless of discovery
# -----------------------------------------------------------------------

IMPLICIT_SENSORS = {
    "version": None,
    "in": "msgs",
    "out": "msgs",
    "crashes": "crashes",
    "flags": None,
}

# -----------------------------------------------------------------------
# Static service buttons (unchanged, hardcoded on purpose)
# -----------------------------------------------------------------------

BUTTONS = [
    ("Check", "check", "ALL"),
    ("Data", "give", "ALL"),
    ("Goodbye", "status", "goodbye"),
    ("Reset", "reset", "ALL"),
    ("Update", "update", "ALL"),
]