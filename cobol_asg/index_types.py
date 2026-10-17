"""The index data item type: a fullword binary holding an occurrence number."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor

INDEX_ITEM = CobolTypeDescriptor(category=CobolDataCategory.BINARY, total_digits=9)
