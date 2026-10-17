"""NIST-85 test harness shared fixtures."""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import cache
from pathlib import Path

import pytest

from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.entry_point import EntryPoint
from interpreter.project.source_file import SourceFile
from interpreter.run import initial_vm_state, run_linked
from interpreter.vm.builtins import core_builtins

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
    "XXXXX051": "SWITCH-1",
    "XXXXX052": "SWITCH-2",
    "XXXXX081": '"12345678"',
    "XXXXX090": "194",
    "XXXXX091": "197",
}
_SWITCH_SETTINGS = {"SWITCH-1": SwitchStatus.ON, "SWITCH-2": SwitchStatus.OFF}
_X_CARD_FILE_RE = re.compile(r"XXXX[XPD](\d{3})")
_COPY_RE = re.compile(r"\bCOPY\s+([\w-]+)", re.IGNORECASE)
_HEADER_RE = re.compile(
    r"^.{6}\*HEADER,COBOL,(\w+),(SUBPRG|SUBRTN),(\w+)", re.MULTILINE
)
_SUBPRG = "SUBPRG"
_SUBRTN = "SUBRTN"
_MAX_STEPS = 2_000_000


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


def _x_card_file(assign_to: str) -> str:
    """The file an ASSIGN names. EXEC85 reads an X-card's number from columns
    17-19 and ignores column 16, so XXXXP001 (passed on) and XXXXD001 (read
    back) are the one file X-card 001 names."""
    return _X_CARD_FILE_RE.sub(r"XXXXX\1", assign_to).lower()


def _source(prog: str) -> str:
    return substitute_x_cards((NIST_DIR / f"{prog}.CBL").read_text())


@cache
def _links() -> tuple[tuple[str, str, str], ...]:
    """Every CCVS *HEADER link: (owner, SUBPRG or SUBRTN, member)."""
    return tuple(
        (m[1], m[2], m[3])
        for path in sorted(NIST_DIR.glob("*.CBL"))
        for m in _HEADER_RE.finditer(path.read_text())
    )


def subroutines(prog: str) -> list[str]:
    """The SUBRTN members of a program: subprograms it CALLs, compiled with it."""
    return [
        member for owner, link, member in _links() if (owner, link) == (prog, _SUBRTN)
    ]


def preceding_run_units(prog: str) -> list[str]:
    """The run units a SUBPRG member follows in its CCVS job: the owner, then
    each earlier member. They create the files this program reads."""
    owners = [
        owner for owner, link, member in _links() if (link, member) == (_SUBPRG, prog)
    ]
    return [
        *owners,
        *(
            member
            for owner, link, member in _links()
            if link == _SUBPRG and owner in owners and member < prog
        ),
    ]


def _copied_members(src: str) -> list[str]:
    """The library text a source COPYs, so file controls inside it are seen."""
    return [
        path.read_text()
        for name in _COPY_RE.findall(_cobol_content(src))
        if (path := NIST_DIR / f"{name.upper()}.CPY").exists()
    ]


def _run_unit(prog: str, tmp_path: Path, max_steps: int) -> Path:
    """Compile a program with its SUBRTN subprograms, run it, return its print path."""
    src = _source(prog)
    callees = [_source(callee) for callee in subroutines(prog)]
    units = [src, *callees]
    provider, print_path = make_provider(
        "\n".join([*units, *(t for unit in units for t in _copied_members(unit))]),
        tmp_path,
        input_deck(NIST_DIR / f"{prog}.DAT"),
    )
    linked = compile_cobol(
        src.encode(),
        parser=make_cobol_parser(copybook_dirs=[NIST_DIR]),
        programs=tuple(
            SourceFile(Path(f"{callee}.CBL"), text.encode())
            for callee, text in zip(subroutines(prog), callees, strict=True)
        ),
        copybook_dirs=[NIST_DIR],
    )
    label = linked.entry_func_label
    run_linked(
        linked,
        entry_point=EntryPoint.function(lambda ref: ref.label == label),
        max_steps=max_steps,
        io_provider=provider,
        builtins=core_builtins(),
        initial_vm=initial_vm_state(io_provider=provider),
    )
    return print_path


def run_nist(prog: str, tmp_path: Path) -> None:
    """Run a CCVS program as its job does, then assert it passed.

    The run units it follows run first in the same directory, so the files they
    pass on are there; their reports are discarded before this program runs.
    """
    if not (NIST_DIR / f"{prog}.CBL").exists():
        pytest.skip(f"NIST source not found: {prog}")
    for unit in preceding_run_units(prog):
        _run_unit(unit, tmp_path, _MAX_STEPS).unlink(missing_ok=True)
    assert_nist_pass(_run_unit(prog, tmp_path, _MAX_STEPS), prog)


def run_display_report(
    prog: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> list[str]:
    """Run a CCVS program that DISPLAYs its report instead of writing a PRINT-FILE,
    and return the lines it displayed."""
    capsys.readouterr()
    _run_unit(prog, tmp_path, _MAX_STEPS)
    return capsys.readouterr().out.splitlines()


def make_provider(
    src: str, tmp_path: Path, system_input: Sequence[str] = ()
) -> tuple[RealFileIOProvider, Path]:
    """Build RealFileIOProvider; return (provider, print_file_path).

    A program with no PRINT file gets a path that is never written.
    """
    overrides = {
        file_name: tmp_path / f"{_x_card_file(assign_to)}.dat"
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
        switches=_SWITCH_SETTINGS,
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


_FLAGS_EXPECTED_RE = re.compile(r"TOTAL NUMBER OF FLAGS EXPECTED = (\d+)\.")


def _comment_lines(src: str) -> list[str]:
    return [
        line[_TEXT_AREA_START:_TEXT_AREA_END].rstrip()
        for line in src.splitlines()
        if len(line) > 6 and line[6] == "*"
    ]


def skip_flagger_program(prog: str, header: str, flags_expected: int) -> None:
    """Classify a CCVS flagger program and skip it with a reason quoting its header.

    A flagger program's verdict is the compiler's FIPS flagging messages, each
    announced by a 'Message expected for above statement' comment and totalled by
    'TOTAL NUMBER OF FLAGS EXPECTED = N.'; it writes no report. The cited header and
    flag total are checked against the source, so the classification cannot drift.
    """
    src_path = NIST_DIR / f"{prog}.CBL"
    if not src_path.exists():
        pytest.skip(f"NIST source not found: {src_path}")
    comments = _comment_lines(src_path.read_text())
    totals = [int(m[1]) for c in comments if (m := _FLAGS_EXPECTED_RE.search(c))]
    assert (header in comments, totals) == (
        True,
        [flags_expected],
    ), f"{prog}: not the flagger program it is classified as"
    pytest.skip(
        f"{prog}: FIPS flagger test (program header: '{header}'; "
        f"'TOTAL NUMBER OF FLAGS EXPECTED = {flags_expected}.') -- its verdict is "
        f"compile-time flagging messages, not run-time output; red-dragon has no "
        f"FIPS flagger"
    )
