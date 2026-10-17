"""SwitchStatus — the two states of an implementor switch."""

from __future__ import annotations

from enum import Enum


class SwitchStatus(Enum):
    ON = "ON"
    OFF = "OFF"
