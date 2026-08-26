# pyright: standard
"""COBOL type descriptors — pure dataclasses for type metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CobolDataCategory(str, Enum):
    """COBOL data type categories supported by the type system.

    These are STORAGE categories, coarser than the PICTURE clause's data
    categories (IBM Enterprise COBOL for z/OS 6.4 Language Reference, "Data
    categories and PICTURE rules", pp. 212-218): the spec's alphabetic category
    is ALPHANUMERIC here, because a PIC A item and a PIC X item are stored and
    moved identically in RedDragon, and the differences the spec does draw
    between them (which senders are legal, class checking) are not modelled.
    The categories with no storage at all here — alphanumeric-edited, external
    floating-point, and the multi-byte DBCS / national / UTF-8 families — are
    refused at field ingestion by pic_parser rather than given a member.
    """

    ZONED_DECIMAL = "ZONED_DECIMAL"
    COMP3 = "COMP3"
    BINARY = "BINARY"
    COMP1 = "COMP1"
    COMP2 = "COMP2"
    ALPHANUMERIC = "ALPHANUMERIC"
    ALPHANUMERIC_EDITED = "ALPHANUMERIC_EDITED"
    NUMERIC_EDITED = "NUMERIC_EDITED"


# The categories whose storage IS their character-position count: one byte per
# character position of the PICTURE character-string.
_DISPLAY_CATEGORIES = frozenset(
    {
        CobolDataCategory.ZONED_DECIMAL,
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ALPHANUMERIC_EDITED,
        CobolDataCategory.NUMERIC_EDITED,
    }
)

# The categories whose CONTENT is characters, so a value read out of one is a
# string and a value moved into one is aligned and space-filled rather than
# converted. Numeric-edited is deliberately absent: its stored form is characters
# but its content is a number being formatted for display.
_CHARACTER_CATEGORIES = frozenset(
    {
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ALPHANUMERIC_EDITED,
    }
)


@dataclass(frozen=True)
class CobolTypeDescriptor:
    """Describes a COBOL data item's type and layout.

    Attributes:
        category: The data category (zoned, comp-3, alphanumeric).
        total_digits: Total digit positions for numeric types,
                      or character length for alphanumeric.
        decimal_digits: Implied decimal positions (0 for integers/alphanumeric).
        signed: Whether the numeric field is signed (S in PIC).
        char_positions: The picture's character-position count, i.e. its DISPLAY
                      size, computed per Table 12 (p. 208). This is what the
                      spec calls "the size of the elementary item", so it is
                      what USAGE DISPLAY storage costs. It differs from
                      total_digits whenever the picture holds symbols that are
                      digit positions but not character positions (P, V) or
                      character positions but not digit positions (insertion
                      characters, and the leading symbol of a floating run).
    """

    category: CobolDataCategory
    total_digits: int
    decimal_digits: int = 0
    signed: bool = False
    char_positions: int = 0
    sign_separate: bool = False
    sign_leading: bool = False
    justified_right: bool = False
    blank_when_zero: bool = False
    # The original PICTURE character-string, kept verbatim. NUMERIC_EDITED needs
    # it for the MOVE-time edit mask (sign/Z/comma/decimal positions); for the
    # other categories it is retained for diagnostics. Empty when there is no
    # PICTURE clause at all (COMP-1, COMP-2, USAGE POINTER).
    pic_string: str = ""

    @property
    def holds_characters(self) -> bool:
        """True for the categories whose content is character data.

        Both alphanumeric and alphanumeric-edited items hold characters, so every
        rule that keys off "is this character data" — comparison as a string,
        MOVE of a zoned sender's digit characters, INITIALIZE to spaces — applies
        to both. Asking the descriptor rather than comparing categories at each
        site is what stops a new character category from being silently routed
        into the numeric paths.
        """
        return self.category in _CHARACTER_CATEGORIES

    @property
    def byte_length(self) -> int:
        """Compute the storage size in bytes for this type.

        - every USAGE DISPLAY category: 1 byte per character position, which is
          exactly char_positions (already including the SIGN SEPARATE byte, and
          already excluding P and V, which the spec does not count in the size).
        - COMP3: packed BCD → (total_digits // 2) + 1 bytes.
        - BINARY: big-endian two's complement → 2/4/8 bytes by digit count.
        - COMP1: IEEE 754 single → 4 bytes (no PIC).
        - COMP2: IEEE 754 double → 8 bytes (no PIC).
        """
        if self.category in _DISPLAY_CATEGORIES:
            # A descriptor built without a picture to analyse — a group item in
            # data_layout, a hand-built fixture — carries its width in
            # total_digits alone, which for character data IS the
            # character-position count. parse_pic always sets char_positions.
            if self.char_positions:
                return self.char_positions
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
        return self.total_digits  # fallback
