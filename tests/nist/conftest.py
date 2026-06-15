"""NIST-85 test harness shared fixtures."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from interpreter.cobol.real_file_provider import RealFileIOProvider

NIST_DIR = Path(
    "/Users/asgupta/code/red-dragon/proleap-bridge/proleap-cobol-parser"
    "/target/test-classes/gov/nist"
)

_ASSIGN_RE = re.compile(r"ASSIGN\s+TO\s+['\"]?(\S+?)['\"]?\s", re.IGNORECASE)


def extract_assign_names(src: str) -> list[str]:
    """Return all ASSIGN TO target names from COBOL source."""
    return _ASSIGN_RE.findall(src)


def make_provider(src: str, tmp_path: Path) -> RealFileIOProvider:
    """Build a RealFileIOProvider mapping every ASSIGN TO name to a tmp file."""
    names = extract_assign_names(src)
    overrides: dict[str, Path] = {}
    for name in names:
        clean = name.strip("'\"").upper()
        overrides[clean] = tmp_path / f"{clean.lower()}.dat"
    return RealFileIOProvider(
        base_dir=tmp_path, file_control=[], path_overrides=overrides
    )


def extract_pass_fail(output: str) -> tuple[int, int]:
    """Count PASS and FAIL occurrences in program output."""
    passes = len(re.findall(r"\bPASS\b", output, re.IGNORECASE))
    fails = len(re.findall(r"\bFAIL\b", output, re.IGNORECASE))
    return passes, fails
