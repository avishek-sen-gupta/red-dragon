"""Shared helpers for COBOL integration tests (ProLeap bridge → IR → CFG → VM).

Centralizes the ProLeap bridge JAR discovery, the env-var fixture, and the
small decode/format helpers used across the COBOL integration test modules so
they are defined exactly once.
"""

from __future__ import annotations

import os

import pytest

JAR_PATH = os.environ.get(
    "PROLEAP_BRIDGE_JAR",
    os.path.expanduser(
        "~/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
    ),
)
JAR_AVAILABLE = os.path.isfile(JAR_PATH)


def to_fixed(lines: list[str]) -> str:
    """Convert short-form COBOL lines to FIXED format (columns 1-80).

    Each input line is treated as starting at column 8 (Area A).
    6 spaces for sequence area + 1 space for indicator area are prepended.
    """
    prefix = "       "  # 7 spaces: cols 1-6 (seq) + col 7 (indicator)
    return "\n".join(prefix + line for line in lines) + "\n"


def decode_zoned_unsigned(region: bytearray, offset: int, length: int) -> int:
    """Decode unsigned zoned decimal from a memory region.

    Each byte is EBCDIC zoned: 0xF0=0, 0xF1=1, ..., 0xF9=9.
    The digit is in the low nibble (b & 0x0F).
    """
    digits = [region[offset + i] & 0x0F for i in range(length)]
    return sum(d * (10 ** (length - 1 - i)) for i, d in enumerate(digits))


@pytest.fixture
def bridge_jar_env():
    """Ensure PROLEAP_BRIDGE_JAR is set for the duration of the fixture.

    Restores the prior value (or unsets) on teardown.
    """
    old = os.environ.get("PROLEAP_BRIDGE_JAR")
    os.environ["PROLEAP_BRIDGE_JAR"] = JAR_PATH
    yield
    if old is None:
        os.environ.pop("PROLEAP_BRIDGE_JAR", None)
    else:
        os.environ["PROLEAP_BRIDGE_JAR"] = old
