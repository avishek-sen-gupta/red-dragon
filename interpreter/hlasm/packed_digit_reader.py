# pyright: standard
"""What a packed read loop needs at each byte: the field address, the byte reader and the not-a-digit table, all set before the loop."""

from dataclasses import dataclass

from interpreter.hlasm.unit_value import UnitReader
from interpreter.register import Register


@dataclass(frozen=True)
class PackedDigitReader:
    address: Register
    read: UnitReader
    not_digits: Register
