# pyright: standard
"""Named constants for COBOL encoding/decoding — eliminates magic hex values and strings."""

from __future__ import annotations

from enum import StrEnum


class NibblePosition(StrEnum):
    """Position of a nibble within a byte."""

    HIGH = "high"
    LOW = "low"


class CobolEncoding(StrEnum):
    """Character encoding schemes for COBOL data."""

    EBCDIC = "ebcdic"
    ASCII = "ascii"


class TallyMode(StrEnum):
    """Counting modes for INSPECT TALLYING."""

    ALL = "all"
    LEADING = "leading"
    CHARACTERS = "characters"


class ReplaceMode(StrEnum):
    """Replacement modes for INSPECT REPLACING."""

    ALL = "all"
    FIRST = "first"
    LEADING = "leading"


class ByteConstants:
    """Hex byte-level constants for COBOL numeric encoding."""

    NIBBLE_MASK = 0x0F
    ZONE_NIBBLE_UNSIGNED = 0xF0
    HIGH_NIBBLE_MASK = 0xF0
    SIGN_NIBBLE_POSITIVE = 0x0C
    SIGN_NIBBLE_NEGATIVE = 0x0D
    SIGN_NIBBLE_UNSIGNED = 0x0F
    SIGN_ZONE_POSITIVE = 0xC0
    SIGN_ZONE_NEGATIVE = 0xD0
    EBCDIC_SPACE = 0x40
    EBCDIC_PLUS = 0x4E
    EBCDIC_MINUS = 0x60
    EBCDIC_SIGN_OFFSET = 0x12  # EBCDIC_MINUS - EBCDIC_PLUS
    BYTE_MASK = 0xFF


class BuiltinName:
    """Names for COBOL primitive builtin functions used in IR operands."""

    NIBBLE_GET = "__nibble_get"
    NIBBLE_SET = "__nibble_set"
    BYTE_FROM_INT = "__byte_from_int"
    INT_FROM_BYTE = "__int_from_byte"
    BYTES_TO_STRING = "__bytes_to_string"
    STRING_TO_BYTES = "__string_to_bytes"
    LIST_GET = "__list_get"
    LIST_SET = "__list_set"
    LIST_LEN = "__list_len"
    LIST_SLICE = "__list_slice"
    LIST_CONCAT = "__list_concat"
    MAKE_LIST = "__make_list"
    COBOL_PREPARE_DIGITS = "__cobol_prepare_digits"
    COBOL_PREPARE_SIGN = "__cobol_prepare_sign"
    STRING_FIND = "__string_find"
    STRING_SPLIT = "__string_split"
    STRING_COUNT = "__string_count"
    STRING_REPLACE = "__string_replace"
    STRING_CONCAT = "__string_concat"
    STRING_CONCAT_PAIR = "__string_concat_pair"
    INT_TO_BINARY_BYTES = "__int_to_binary_bytes"
    BINARY_BYTES_TO_INT = "__binary_bytes_to_int"
    FLOAT_TO_BYTES = "__float_to_bytes"
    BYTES_TO_FLOAT = "__bytes_to_float"
    COBOL_BLANK_WHEN_ZERO = "__cobol_blank_when_zero"


class InspectType:
    """INSPECT statement type identifiers."""

    TALLYING = "TALLYING"
    REPLACING = "REPLACING"


class DelimiterMode:
    """STRING DELIMITED BY mode identifiers."""

    SIZE = "SIZE"
