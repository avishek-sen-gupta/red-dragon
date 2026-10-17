"""The encoding a SORT or MERGE key's bytes are compared in, from its layout."""

from __future__ import annotations

from collections.abc import Mapping

from cobol_asg.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.sort_key_encoding import SortKeyEncoding

_BY_CATEGORY: Mapping[CobolDataCategory, SortKeyEncoding] = {
    CobolDataCategory.ALPHANUMERIC: SortKeyEncoding.ALPHANUMERIC,
}


def sort_key_encoding(layout: FieldLayout) -> SortKeyEncoding:
    return _BY_CATEGORY[layout.type_descriptor.category]
