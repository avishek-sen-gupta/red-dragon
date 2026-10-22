# pyright: standard
"""What an edit works on: the pattern and source addresses, the byte reader and the fill byte."""

from dataclasses import dataclass

from interpreter.hlasm.unit_value import UnitReader
from interpreter.register import Register


@dataclass(frozen=True)
class EditOperands:
    pattern: Register
    source: Register
    read: UnitReader
    fill: Register
