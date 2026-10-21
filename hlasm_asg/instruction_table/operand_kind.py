# pyright: standard
"""What an instruction operand denotes."""

from __future__ import annotations

from enum import StrEnum


class OperandKind(StrEnum):
    DISP = "DISP"
    DISP_IDX = "DISP_IDX"
    IMM = "IMM"
    MASK = "MASK"
    REG = "REG"
    RELOC_IMM = "RELOC_IMM"
    VEC_REG = "VEC_REG"
