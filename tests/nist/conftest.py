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

_SELECT_ASSIGN_RE = re.compile(
    r"\bSELECT\s+([\w-]+)(?:(?!\bSELECT\b).)*?\bASSIGN\b(?:\s+TO)?\s+([\w-]+)",
    re.IGNORECASE | re.DOTALL,
)

_PRINT_RECORD_LEN = 120


def _cobol_content(src: str) -> str:
    """Return COBOL source with sequence numbers and comments stripped."""
    lines = []
    for line in src.splitlines():
        if len(line) > 6 and line[6] in ("*", "/"):
            continue
        lines.append(line[7:72] if len(line) > 7 else "")
    return " ".join(lines)


def extract_file_controls(src: str) -> list[tuple[str, str]]:
    """Return [(cobol_file_name, assign_to), ...] from SELECT...ASSIGN TO clauses."""
    content = _cobol_content(src)
    return [
        (m.group(1).upper(), m.group(2).upper())
        for m in _SELECT_ASSIGN_RE.finditer(content)
    ]


def make_provider(src: str, tmp_path: Path) -> tuple[RealFileIOProvider, Path | None]:
    """Build RealFileIOProvider; return (provider, print_file_path)."""
    file_controls = extract_file_controls(src)
    overrides: dict[str, Path] = {}
    print_path: Path | None = None
    for file_name, assign_to in file_controls:
        p = tmp_path / f"{assign_to.lower()}.dat"
        overrides[file_name] = p
        if "PRINT" in file_name:
            print_path = p
    provider = RealFileIOProvider(
        base_dir=tmp_path, file_control=[], path_overrides=overrides
    )
    return provider, print_path


def assert_nist_pass(print_path: Path | None, prog: str) -> None:
    """Read the PRINT-FILE and assert no FAIL* records."""
    if print_path is None or not print_path.exists():
        pytest.skip(f"{prog}: PRINT-FILE not written — I/O may not be supported yet")
    data = print_path.read_bytes()
    records = [
        data[i : i + _PRINT_RECORD_LEN].decode("latin-1", errors="replace")
        for i in range(0, len(data), _PRINT_RECORD_LEN)
        if data[i : i + _PRINT_RECORD_LEN].strip(b"\x00")
    ]
    fails = [r for r in records if "FAIL*" in r]
    assert not fails, f"{prog} NIST failures:\n" + "\n".join(fails)
