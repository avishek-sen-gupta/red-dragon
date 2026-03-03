"""COBOL type descriptors — pure dataclasses for type metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CobolDataCategory(str, Enum):
    """COBOL data type categories supported by the type system."""

    ZONED_DECIMAL = "ZONED_DECIMAL"
    COMP3 = "COMP3"
    BINARY = "BINARY"
    COMP1 = "COMP1"
    COMP2 = "COMP2"
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
    sign_separate: bool = False
    sign_leading: bool = False
    justified_right: bool = False
    blank_when_zero: bool = False

    @property
    def byte_length(self) -> int:
        """Compute the storage size in bytes for this type.

        - ZONED_DECIMAL: 1 byte per digit → total_digits bytes.
        - COMP3: packed BCD → (total_digits // 2) + 1 bytes.
        - BINARY: big-endian two's complement → 2/4/8 bytes by digit count.
        - COMP1: IEEE 754 single → 4 bytes (no PIC).
        - COMP2: IEEE 754 double → 8 bytes (no PIC).
        - ALPHANUMERIC: 1 byte per character → total_digits bytes.
        """
        if self.category == CobolDataCategory.ZONED_DECIMAL:
            return self.total_digits + (1 if self.sign_separate else 0)
        if self.category == CobolDataCategory.COMP3:
            return (self.total_digits // 2) + 1
        if self.category == CobolDataCategory.BINARY:
            if self.total_digits <= 4:
                return 2
            if self.total_digits <= 9:
                return 4
            return 8
        if self.category == CobolDataCategory.COMP1:
            return 4
        if self.category == CobolDataCategory.COMP2:
            return 8
        if self.category == CobolDataCategory.ALPHANUMERIC:
            return self.total_digits
        return self.total_digits  # fallback
