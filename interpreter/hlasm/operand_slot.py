# pyright: standard
"""Whether an operand is a storage address or a value field, which tells instruction shapes of one format apart."""

from enum import Enum


class OperandSlot(Enum):
    VALUE = "V"
    STORAGE = "S"
