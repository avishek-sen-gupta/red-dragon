# pyright: standard
"""A signed-packed-decimal field: its address and its length in bytes, both run-time registers."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class PackedField:
    address: Register
    length: Register
