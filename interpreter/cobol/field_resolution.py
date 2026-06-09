# pyright: standard
"""Field reference resolution — subscript parsing and offset computation."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.data_layout import FieldLayout
from interpreter.register import Register


@dataclass(frozen=True)
class ResolvedFieldRef:
    """Result of resolving a field reference, possibly with a subscript.

    Attributes:
        fl: The FieldLayout for the base field.
        offset_reg: Register holding the computed byte offset.
            For bare refs, this is a CONST of fl.offset.
            For subscripted refs, this is base + (idx - 1) * element_size.
    """

    fl: FieldLayout
    offset_reg: Register
