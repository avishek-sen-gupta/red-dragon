"""Shared helpers for COBOL integration tests (ProLeap bridge → IR → CFG → VM).

Centralizes the ProLeap bridge JAR discovery, the env-var fixture, and the
small decode/format helpers used across the COBOL integration test modules so
they are defined exactly once.
"""

from __future__ import annotations

import os

import pytest

from interpreter.run import run

JAR_PATH = os.environ.get(
    "PROLEAP_BRIDGE_JAR",
    os.path.expanduser(
        "~/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
    ),
)
JAR_AVAILABLE = os.path.isfile(JAR_PATH)


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


def run_cobol(lines: list[str], max_steps: int = 1000):
    """Run short-form COBOL lines through the full pipeline; return the VMState."""
    source = to_fixed(lines)
    return run(source=source, language="cobol", max_steps=max_steps)


def first_region(vm):
    """Return the first memory region from the VM state."""
    return vm.region_get(list(vm.region_keys())[0])


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
