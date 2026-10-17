# pyright: standard
"""COBOL figurative constants — maps COBOL keywords to Python string equivalents."""

from __future__ import annotations

from interpreter.cobol.ebcdic_table import EbcdicTable

# The character the EBCDIC byte 0xFF decodes to, so HIGH-VALUE compares equal to
# a decoded field holding 0xFF and encodes back to 0xFF.
_HIGH_VALUE = chr(EbcdicTable.EBCDIC_TO_ASCII[0xFF])

COBOL_FIGURATIVE_CONSTANTS: dict[str, str] = {
    "SPACE": " ",
    "SPACES": " ",
    "ZERO": "0",
    "ZEROS": "0",
    "ZEROES": "0",
    "QUOTE": '"',
    "QUOTES": '"',
    "LOW-VALUE": "\x00",
    "LOW-VALUES": "\x00",
    "HIGH-VALUE": _HIGH_VALUE,
    "HIGH-VALUES": _HIGH_VALUE,
}


def repeat_to_width(pattern: str, width: int) -> str:
    return (pattern * (width // len(pattern) + 1))[:width]
