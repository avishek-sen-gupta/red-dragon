"""NIST-85 test harness shared fixtures."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import pytest

from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.real_file_provider import RealFileIOProvider

NIST_DIR = (
    Path(__file__).resolve().parents[2]
    / "proleap-bridge/proleap-cobol-parser/src/test/resources/gov/nist"
)

_SELECT_ASSIGN_RE = re.compile(
    r"\bSELECT\s+([\w-]+)(?:(?!\bSELECT\b).)*?\bASSIGN\b(?:\s+TO)?\s+([\w-]+)",
    re.IGNORECASE | re.DOTALL,
)

_PRINT_RECORD_LEN = 120
_NO_PRINT_FILE = "no-print-file.dat"
_TEXT_AREA_START = 7
_TEXT_AREA_END = 72
_INPUT_RECORD_LEN = 80
_DECK_MARKERS = ("*HEADER,", "*END-OF,")
_X_CARD_RE = re.compile(r"XXXXX\d{3}")
_X_CARDS = {
    "XXXXX081": '"12345678"',
}


def _with_x_cards(line: str) -> str:
    text_area = line[_TEXT_AREA_START:_TEXT_AREA_END]
    substituted = _X_CARD_RE.sub(lambda m: _X_CARDS.get(m[0], m[0]), text_area)
    if substituted == text_area:
        return line
    width = _TEXT_AREA_END - _TEXT_AREA_START
    assert len(substituted.rstrip()) <= width, f"X-card overflows: {line!r}"
    return (
        line[:_TEXT_AREA_START]
        + substituted.rstrip().ljust(width)
        + line[_TEXT_AREA_END:]
    )


def substitute_x_cards(src: str) -> str:
    """Replace each X-card placeholder that has a value, as the CCVS
    extraction step does, keeping every line's sequence area in place."""
    return "\n".join(_with_x_cards(line) for line in src.splitlines())


def input_deck(deck_path: Path) -> list[str]:
    """The data cards of a program's CCVS input deck, as 80-column records."""
    if not deck_path.exists():
        return []
    return [
        line[:_INPUT_RECORD_LEN].ljust(_INPUT_RECORD_LEN)
        for line in deck_path.read_text().splitlines()
        if not line[6:].startswith(_DECK_MARKERS)
    ]


def _cobol_content(src: str) -> str:
    """Return COBOL source with sequence numbers and comments stripped."""
    return " ".join(
        line[7:72] if len(line) > 7 else ""
        for line in src.splitlines()
        if not (len(line) > 6 and line[6] in ("*", "/"))
    )


def extract_file_controls(src: str) -> list[tuple[str, str]]:
    """Return [(cobol_file_name, assign_to), ...] from SELECT...ASSIGN TO clauses."""
    content = _cobol_content(src)
    return [
        (m.group(1).upper(), m.group(2).upper())
        for m in _SELECT_ASSIGN_RE.finditer(content)
    ]


def make_provider(
    src: str, tmp_path: Path, system_input: Sequence[str] = ()
) -> tuple[RealFileIOProvider, Path]:
    """Build RealFileIOProvider; return (provider, print_file_path).

    A program with no PRINT file gets a path that is never written.
    """
    overrides = {
        file_name: tmp_path / f"{assign_to.lower()}.dat"
        for file_name, assign_to in extract_file_controls(src)
    }
    print_path = next(
        (path for file_name, path in overrides.items() if "PRINT" in file_name),
        tmp_path / _NO_PRINT_FILE,
    )
    provider = RealFileIOProvider(
        base_dir=tmp_path,
        file_control=[],
        path_overrides=overrides,
        system_input=system_input,
    )
    return provider, print_path


# CCVS programs close each run with a summary block. A genuine pass must:
#   1. reach completion          -> the "END OF TEST" banner is written
#   2. report zero failed tests  -> "NNN TEST(S) FAILED" with NNN == 0 (or "NO"),
#      or, for a visual-inspection program, "NNN TESTS REQUIRE VISUAL INSPECTION"
#   3. carry no inline failures  -> no detail line contains "FAIL*"
# Checking only (3) lets a program that halts after the header — or one whose
# own summary admits failures — masquerade as a pass. See red-dragon-m0oa.7.
_END_OF_TEST = "END OF TEST"
_TESTS_FAILED_RE = re.compile(r"(\d+|NO)\s+TEST\(S\)\s+FAILED", re.IGNORECASE)
_VISUAL_INSPECTION_RE = re.compile(
    r"\d+\s+TESTS\s+REQUIRE\s+VISUAL\s+INSPECTION", re.IGNORECASE
)


def _summary_failed_count(text: str, prog: str) -> int:
    counts = _TESTS_FAILED_RE.findall(text)
    if counts == [] and _VISUAL_INSPECTION_RE.search(text):
        return 0
    assert counts != [], (
        f"{prog}: completion banner present but no 'TEST(S) FAILED' summary line "
        f"found — cannot confirm a clean run."
    )
    return 0 if counts[0].upper() == "NO" else int(counts[0])


def _print_records(data: bytes) -> list[str]:
    return [
        EbcdicTable.ebcdic_to_ascii(data[i : i + _PRINT_RECORD_LEN]).decode("latin-1")
        for i in range(0, len(data), _PRINT_RECORD_LEN)
        if data[i : i + _PRINT_RECORD_LEN].strip(b"\x00")
    ]


def assert_nist_pass(print_path: Path, prog: str) -> None:
    """Assert a NIST CCVS program ran to completion and reported zero failures.

    Skips only when no PRINT-FILE was produced at all (the program could not
    start — e.g. an M-stub awaiting external input). Any program that does write
    output must complete and report a clean summary, or this fails.
    """
    if not print_path.exists():
        pytest.skip(f"{prog}: PRINT-FILE not written — program did not produce output")

    records = _print_records(print_path.read_bytes())
    text = "\n".join(records)

    # (1) Completion: the CCVS end-of-test banner must be present.
    assert _END_OF_TEST in text, (
        f"{prog}: did not run to completion — '{_END_OF_TEST}' banner absent "
        f"({len(records)} record(s) written). Program halted before its summary."
    )

    # (2) Summary failure count must be zero.
    n_failed = _summary_failed_count(text, prog)
    assert n_failed == 0, f"{prog}: CCVS summary reports {n_failed} failed test(s)."

    # (3) No inline failure markers in the detail lines.
    inline_fails = [r for r in records if "FAIL*" in r]
    assert not inline_fails, f"{prog}: inline FAIL* records:\n" + "\n".join(
        inline_fails
    )
