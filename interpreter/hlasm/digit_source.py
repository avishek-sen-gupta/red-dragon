# pyright: standard
"""Where a pack takes its digits: the source address, the offset of its rightmost byte and the bytes per digit, the digit in each unit's rightmost four bits."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class DigitSource:
    address: Register
    last: Register
    stride: int
