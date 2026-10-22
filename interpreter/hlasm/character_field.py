# pyright: standard
"""Where an unpack puts its digits: the target address, its length in bytes, the bytes per character and the zone each digit is extended with."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class CharacterField:
    address: Register
    length: Register
    width: int
    zone: int
