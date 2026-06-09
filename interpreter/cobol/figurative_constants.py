# pyright: standard
"""COBOL figurative constants — maps COBOL keywords to Python string equivalents."""

from __future__ import annotations

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
    "HIGH-VALUE": "\xff",
    "HIGH-VALUES": "\xff",
}


def translate_cobol_figurative(value: str) -> str:
    """Translate COBOL figurative constants to their Python equivalents."""
    return COBOL_FIGURATIVE_CONSTANTS.get(value, value)


# Figurative constants whose semantics are RAW bytes, not character data:
# HIGH-VALUES is 0xFF in every receiver position (the highest collating byte),
# LOW-VALUES is 0x00. These must bypass ASCII→EBCDIC translation — otherwise the
# fill char (\xff/\x00) round-trips through encode(errors="replace") and becomes
# an EBCDIC '?'/space (red-dragon-raxa). SPACES/ZEROS/QUOTES remain character
# data and go through the normal encode path.
COBOL_RAW_FIGURATIVE_BYTES: dict[str, int] = {
    "HIGH-VALUE": 0xFF,
    "HIGH-VALUES": 0xFF,
    "LOW-VALUE": 0x00,
    "LOW-VALUES": 0x00,
}


def raw_figurative_byte(value: str) -> int | None:
    """Return the raw fill byte for HIGH-VALUES/LOW-VALUES, else ``None``.

    A non-None result means the figurative constant denotes raw bytes that must
    fill the receiver's full width verbatim (no EBCDIC translation).
    """
    return COBOL_RAW_FIGURATIVE_BYTES.get(value.upper())
