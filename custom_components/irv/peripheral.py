"""Peripheral data model + discovery payload parsing.

Deliberately free of any Home Assistant imports so it can be reasoned about
(and tested) independently of a running HA instance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging

from .const import (
    BME_SUBSENSORS,
    IMPLICIT_SENSORS,
    TYPE_BME,
    TYPE_DHT,
    TYPE_SWITCH,
    TYPE_SENSOR,
    TYPE_SGREADY,
    TYPE_BINARYSENSOR,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class Peripheral:
    """A single controllable/reportable thing on a board."""

    board: str
    ptype: str
    name: str

    pin: int | None = None
    inverted: bool | None = None

    # RELE / VENTIL
    value_on: str | None = None
    value_off: str | None = None

    # plain sensors (DHT / BME sub-sensors / implicit debug sensors)
    # None means "unit arrives with each report" (DHT) or "genuinely unitless" (version)
    unit: str | None = None

    # SGREADY 4-way labels
    value00: str | None = None
    value01: str | None = None
    value10: str | None = None
    value11: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.board, self.name)


def _sensor(board: str, name: str, unit: str | None) -> Peripheral:
    return Peripheral(board=board, ptype=TYPE_SENSOR, name=name, unit=unit)


def parse_discovery_payload(board: str, data: dict) -> list[Peripheral]:
    """Parse a decoded 'discovery/<board>' MQTT payload into Peripherals.

    Always injects the 3 implicit debug sensors (version, in, out) and
    expands any BME entry into its 4 constituent sub-sensors, since the
    board reports those as separate keys (e.g. "bme/teplota").
    """
    peripherals: list[Peripheral] = []

    # Implicit debug sensors present on every board.
    for name, unit in IMPLICIT_SENSORS.items():
        peripherals.append(_sensor(board, name, unit))

    raw_list = data.get("PERIPHERALS", []) or []

    for raw in raw_list:
        ptype = str(raw.get("TYPE") or "").upper()
        name = raw.get("NAME")

        if not name:
            _LOGGER.warning(
                "IRV: peripheral without NAME in discovery for board '%s': %s",
                board,
                raw,
            )
            continue

        if ptype == TYPE_BME:
            for sub, unit in BME_SUBSENSORS.items():
                peripherals.append(_sensor(board, f"{name}/{sub}", unit))
            continue

        if ptype == TYPE_DHT:
            # Unit arrives with each report, not with discovery.
            peripherals.append(_sensor(board, name, None))
            continue

        if ptype in (TYPE_SWITCH, TYPE_BINARYSENSOR):
            peripherals.append(
                Peripheral(
                    board=board,
                    ptype=ptype,
                    name=name,
                    pin=raw.get("PIN"),
                    inverted=raw.get("INVERTED"),
                    value_on=raw.get("VALUEON"),
                    value_off=raw.get("VALUEOFF"),
                )
            )
            continue

        if ptype == TYPE_SGREADY:
            peripherals.append(
                Peripheral(
                    board=board,
                    ptype=ptype,
                    name=name,
                    pin=raw.get("PIN"),
                    value00=raw.get("VALUE00", "00"),
                    value01=raw.get("VALUE01", "01"),
                    value10=raw.get("VALUE10", "10"),
                    value11=raw.get("VALUE11", "11"),
                )
            )
            continue

        _LOGGER.warning(
            "IRV: unknown peripheral TYPE '%s' for %s/%s, ignoring",
            ptype,
            board,
            name,
        )

    return peripherals
