"""The two pointer field types: a signed binary fullword or doubleword."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor

FULLWORD_POINTER = CobolTypeDescriptor(
    category=CobolDataCategory.BINARY,
    total_digits=9,
    signed=True,
    char_positions=9,
    pic_string="S9(9)",
)
DOUBLEWORD_POINTER = CobolTypeDescriptor(
    category=CobolDataCategory.BINARY,
    total_digits=18,
    signed=True,
    char_positions=18,
    pic_string="S9(18)",
)
