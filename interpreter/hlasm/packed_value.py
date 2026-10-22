# pyright: standard
"""A signed-packed-decimal field as read: its magnitude, its negative bit (sign B or D) and its invalid bit (a bad digit or sign), each an int register."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class PackedValue:
    magnitude: Register
    negative: Register
    invalid: Register
