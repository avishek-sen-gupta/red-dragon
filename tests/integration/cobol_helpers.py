"""Shared helpers for COBOL integration tests (ProLeap bridge → IR → CFG → VM).

Centralizes the ProLeap bridge JAR path fixture (``bridge_jar``) and the small
decode/format helpers used across the COBOL integration test modules so they are
defined exactly once.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from interpreter.run import run

_AREA_A = "       "  # 7 spaces: cols 1-6 (seq) + col 7 (indicator = space)
_COMMENT = "      *"  # col 7 = * for comment line


def to_fixed(lines: list[str]) -> str:
    """Convert short-form COBOL lines to FIXED format (columns 1-80).

    Each input line is treated as starting at column 8 (Area A): 6 spaces for
    the sequence area + 1 space for the indicator area are prepended.

    A line starting with ``*`` is emitted as a COBOL comment line (the ``*``
    goes in the column-7 indicator area); the rest of the line follows.
    """
    formatted = [
        _COMMENT + line[1:] if line.startswith("*") else _AREA_A + line
        for line in lines
    ]
    return "\n".join(formatted) + "\n"


def decode_zoned_unsigned(region: bytearray, offset: int, length: int) -> int:
    """Decode unsigned zoned decimal from a memory region.

    Each byte is EBCDIC zoned: 0xF0=0, 0xF1=1, ..., 0xF9=9.
    The digit is in the low nibble (b & 0x0F).
    """
    digits = [region[offset + i] & 0x0F for i in range(length)]
    return sum(d * (10 ** (length - 1 - i)) for i, d in enumerate(digits))


def decode_zoned_with_decimal(
    region: bytearray, offset: int, integer_digits: int, decimal_digits: int
) -> Decimal:
    """Decode zoned decimal with fixed-point (integer.fractional) parts.

    Extracts (integer_digits + decimal_digits) zoned decimal bytes, then
    divides by 10^decimal_digits to place the decimal point.
    E.g., 3 integer + 2 decimal digits reads 5 bytes and divides by 100.
    """
    n = integer_digits + decimal_digits
    digits = [region[offset + i] & 0x0F for i in range(n)]
    raw = sum(d * (10 ** (n - 1 - i)) for i, d in enumerate(digits))
    return Decimal(raw) / Decimal(10**decimal_digits)


def run_cobol(lines: list[str], max_steps: int = 1000):
    """Run short-form COBOL lines through the full pipeline; return the VMState."""
    source = to_fixed(lines)
    return run(source=source, language="cobol", max_steps=max_steps)


def first_region(vm):
    """Return the first memory region from the VM state."""
    return vm.region_get(list(vm.region_keys())[0])


def all_field_names(fields) -> set[str]:
    """Recursively collect all field names from a list of CobolFields."""
    names: set[str] = set()
    for f in fields:
        names.add(f.name)
        names |= all_field_names(f.children)
    return names


@pytest.fixture
def bridge_jar() -> str:
    """The ProLeap bridge JAR path — the single source of the JAR config, read from
    the required PROLEAP_BRIDGE_JAR env. No default, no skip: if it's unset, a test
    that needs the JAR fails loudly (KeyError) instead of silently skipping or
    guessing a path. Fixtures/tests that build a parser take this and use the
    returned path; run()/compile_directory read the same env var themselves.
    """
    return os.environ["PROLEAP_BRIDGE_JAR"]
