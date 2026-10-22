# pyright: standard
"""One Unicode conversion step's operands: each operand's address, the offset reached in it and the bytes left after that offset."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class ConversionCursor:
    source: Register
    source_at: Register
    source_left: Register
    target: Register
    target_at: Register
    target_left: Register
