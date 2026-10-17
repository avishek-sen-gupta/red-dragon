"""The encoding a SORT or MERGE key's bytes are compared in, from its layout."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.sort_key_encoding import SortKeyEncoding

_ZONED: Mapping[tuple[bool, bool], SortKeyEncoding] = {
    (False, False): SortKeyEncoding.ZONED_TRAILING,
    (False, True): SortKeyEncoding.ZONED_LEADING,
    (True, False): SortKeyEncoding.ZONED_TRAILING_SEPARATE,
    (True, True): SortKeyEncoding.ZONED_LEADING_SEPARATE,
}

_BINARY: Mapping[bool, SortKeyEncoding] = {
    True: SortKeyEncoding.BINARY_SIGNED,
    False: SortKeyEncoding.BINARY_UNSIGNED,
}

_BY_CATEGORY: Mapping[
    CobolDataCategory, Callable[[CobolTypeDescriptor], SortKeyEncoding]
] = {
    CobolDataCategory.ALPHANUMERIC: lambda td: SortKeyEncoding.ALPHANUMERIC,
    CobolDataCategory.ALPHANUMERIC_EDITED: lambda td: SortKeyEncoding.ALPHANUMERIC,
    CobolDataCategory.NUMERIC_EDITED: lambda td: SortKeyEncoding.ALPHANUMERIC,
    CobolDataCategory.ZONED_DECIMAL: lambda td: _ZONED[
        (td.sign_separate, td.sign_leading)
    ],
    CobolDataCategory.COMP3: lambda td: SortKeyEncoding.PACKED,
    CobolDataCategory.BINARY: lambda td: _BINARY[td.signed],
    CobolDataCategory.COMP1: lambda td: SortKeyEncoding.FLOAT_SHORT,
    CobolDataCategory.COMP2: lambda td: SortKeyEncoding.FLOAT_LONG,
}


def sort_key_encoding(layout: FieldLayout) -> SortKeyEncoding:
    return _BY_CATEGORY[layout.type_descriptor.category](layout.type_descriptor)
