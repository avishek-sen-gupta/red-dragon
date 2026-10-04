"""OperandKind — what a SET operand is."""

from __future__ import annotations

from enum import Enum


class OperandKind(Enum):
    REF = "ref"
    ADDRESS_OF = "address_of"
    LENGTH_OF = "length_of"
    FIGURATIVE = "figurative"
    LIT = "lit"
