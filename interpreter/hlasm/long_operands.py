# pyright: standard
"""The first- and second-operand addresses and lengths of a long move or compare, read from their register pairs before anything is stored, and the shorter length."""

from dataclasses import dataclass

from interpreter.register import Register


@dataclass(frozen=True)
class LongOperands:
    first: Register
    first_length: Register
    second: Register
    second_length: Register
    shorter: Register
