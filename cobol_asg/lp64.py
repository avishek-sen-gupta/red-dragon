"""Lp64 — 8-byte pointers, LP(64)."""

from __future__ import annotations

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.cobol_types import CobolTypeDescriptor
from cobol_asg.pointer_types import DOUBLEWORD_POINTER


class Lp64(AddressingMode):
    @property
    def pointer_type(self) -> CobolTypeDescriptor:
        return DOUBLEWORD_POINTER
