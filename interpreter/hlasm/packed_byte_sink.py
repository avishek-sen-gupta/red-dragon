# pyright: standard
"""Where a packed store loop writes one byte at a time: the field address and the constant one-byte length, set before the loop."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class PackedByteSink:
    address: Register
    single: Register
