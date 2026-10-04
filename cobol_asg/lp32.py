"""Lp32 — 4-byte pointers, IBM's default LP(32)."""

from __future__ import annotations

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.cobol_types import CobolTypeDescriptor
from cobol_asg.pointer_types import FULLWORD_POINTER


class Lp32(AddressingMode):
    @property
    def pointer_type(self) -> CobolTypeDescriptor:
        return FULLWORD_POINTER


LP32_MODE = Lp32()
