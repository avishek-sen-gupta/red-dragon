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
