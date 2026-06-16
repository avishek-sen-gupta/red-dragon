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


# CCVS programs close each run with a summary block. A genuine pass must:
#   1. reach completion          -> the "END OF TEST" banner is written
#   2. report zero failed tests  -> "NNN TEST(S) FAILED" with NNN == 0 (or "NO")
#   3. carry no inline failures  -> no detail line contains "FAIL*"
# Checking only (3) lets a program that halts after the header — or one whose
# own summary admits failures — masquerade as a pass. See red-dragon-m0oa.7.
_END_OF_TEST = "END OF TEST"
_TESTS_FAILED_RE = re.compile(r"(\d+|NO)\s+TEST\(S\)\s+FAILED", re.IGNORECASE)


def assert_nist_pass(print_path: Path | None, prog: str) -> None:
    """Assert a NIST CCVS program ran to completion and reported zero failures.

    Skips only when no PRINT-FILE was produced at all (the program could not
    start — e.g. an M-stub awaiting external input). Any program that does write
    output must complete and report a clean summary, or this fails.
    """
    if print_path is None or not print_path.exists():
        pytest.skip(f"{prog}: PRINT-FILE not written — program did not produce output")

    data = print_path.read_bytes()
    records = [
        data[i : i + _PRINT_RECORD_LEN].decode("latin-1", errors="replace")
        for i in range(0, len(data), _PRINT_RECORD_LEN)
        if data[i : i + _PRINT_RECORD_LEN].strip(b"\x00")
    ]
    text = "\n".join(records)

    # (1) Completion: the CCVS end-of-test banner must be present.
    assert _END_OF_TEST in text, (
        f"{prog}: did not run to completion — '{_END_OF_TEST}' banner absent "
        f"({len(records)} record(s) written). Program halted before its summary."
    )

    # (2) Summary failure count must be zero.
    m = _TESTS_FAILED_RE.search(text)
    assert m is not None, (
        f"{prog}: completion banner present but no 'TEST(S) FAILED' summary line "
        f"found — cannot confirm a clean run."
    )
    n_failed = 0 if m.group(1).upper() == "NO" else int(m.group(1))
    assert n_failed == 0, f"{prog}: CCVS summary reports {n_failed} failed test(s)."

    # (3) No inline failure markers in the detail lines.
    inline_fails = [r for r in records if "FAIL*" in r]
    assert not inline_fails, f"{prog}: inline FAIL* records:\n" + "\n".join(
        inline_fails
    )
