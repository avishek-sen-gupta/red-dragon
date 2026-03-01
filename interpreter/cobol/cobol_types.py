"""COBOL type descriptors — pure dataclasses for type metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CobolDataCategory(str, Enum):
    """COBOL data type categories supported by the type system."""

    ZONED_DECIMAL = "ZONED_DECIMAL"
    COMP3 = "COMP3"
    ALPHANUMERIC = "ALPHANUMERIC"


@dataclass(frozen=True)
class CobolTypeDescriptor:
    """Describes a COBOL data item's type and layout.

    Attributes:
        category: The data category (zoned, comp-3, alphanumeric).
        total_digits: Total digit positions for numeric types,
                      or character length for alphanumeric.
        decimal_digits: Implied decimal positions (0 for integers/alphanumeric).
        signed: Whether the numeric field is signed (S in PIC).
    """

    category: CobolDataCategory
    total_digits: int
    decimal_digits: int = 0
    signed: bool = False

    @property
    def byte_length(self) -> int:
        """Compute the storage size in bytes for this type.

        - ZONED_DECIMAL: 1 byte per digit → total_digits bytes.
        - COMP3: packed BCD → (total_digits // 2) + 1 bytes.
        - ALPHANUMERIC: 1 byte per character → total_digits bytes.
        """
        if self.category == CobolDataCategory.ZONED_DECIMAL:
            return self.total_digits
        if self.category == CobolDataCategory.COMP3:
            return (self.total_digits // 2) + 1
        if self.category == CobolDataCategory.ALPHANUMERIC:
            return self.total_digits
        return self.total_digits  # fallback
