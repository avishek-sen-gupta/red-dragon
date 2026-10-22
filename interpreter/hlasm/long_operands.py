# pyright: standard
"""The first- and source-operand addresses and lengths of a long move, read from their register pairs before anything is stored, and the count moved: the smaller length."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class LongOperands:
    target: Register
    target_length: Register
    source: Register
    source_length: Register
    moved: Register
