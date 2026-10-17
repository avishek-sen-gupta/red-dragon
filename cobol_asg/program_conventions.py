"""The per-program facts every item's picture and usage are read under."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.cobol_types import CobolTypeDescriptor
from cobol_asg.edit_picture import DEFAULT_CURRENCY
from cobol_asg.pointer_types import FULLWORD_POINTER


@dataclass(frozen=True)
class ProgramConventions:
    """CURRENCY SIGN, DECIMAL-POINT IS COMMA, and the addressing mode's pointer type."""

    currency: str = DEFAULT_CURRENCY
    pointer_type: CobolTypeDescriptor = FULLWORD_POINTER
    decimal_point_is_comma: bool = False


DEFAULT_CONVENTIONS = ProgramConventions()
