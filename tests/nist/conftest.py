"""NIST-85 harness: shared fixtures, and the typed outcome each test reports."""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Generator, Mapping, Sequence
from functools import cache
from pathlib import Path

import pytest

from cobol_asg.cobol_parser import ProLeapCobolParser
from cobol_asg.copybook_library import CopybookLibrary
from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.cobol.run_inputs import RunInputs
from interpreter.encoding.ebcdic_table import EbcdicTable
from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.entry_point import EntryPoint
from interpreter.project.source_file import SourceFile
from interpreter.run import (
    BudgetExhausted,
    RunOutcome,
    initial_vm_state,
    run_linked_resumable,
)
from interpreter.vm.builtins import core_builtins
from tests.nist.nist_classify import nist_result
from tests.nist.nist_failure import NistFailure
from tests.nist.nist_option import OptionSelection
from tests.nist.nist_outcome import NistOutcome
from tests.nist.nist_skip import NistSkip

NIST_DIR = (
    Path(__file__).resolve().parents[2]
    / "proleap-bridge/proleap-cobol-parser/src/test/resources/gov/nist"
)

_SELECT_ASSIGN_RE = re.compile(
    r"\bSELECT\s+(?:OPTIONAL\s+)?([\w-]+)"
    r"(?:(?!\bSELECT\b).)*?\bASSIGN\b(?:\s+TO)?\s+([\w-]+)",
    re.IGNORECASE | re.DOTALL,
)

_PRINT_RECORD_LEN = 120
_NO_PRINT_FILE = "no-print-file.dat"
_TEXT_AREA_START = 7
_TEXT_AREA_END = 72
_INPUT_RECORD_LEN = 80
_DECK_MARKERS = ("*HEADER,", "*END-OF,")
_X_CARD_RE = re.compile(r"(?<![\w-])XXXXX\d{3}(?![\w-])")
_X_CARDS = {
    "XXXXX051": "SWITCH-1",
    "XXXXX052": "SWITCH-2",
    "XXXXX063": '" .<(+$$*);-/,>=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"',
    "XXXXX064": '"9876543210ZYXWVUTSRQPONMLKJIHGFEDCBA=>,/-;)*$$+(<. "',
    "XXXXX065": "0200",
    "XXXXX081": '"12345678"',
    "XXXXX090": "194",
    "XXXXX091": "197",
}
_X_CARD_LIBRARIES = {
    "XXXXX047": {"ALTLB": "ALTLB"},
    "XXXXX048": {"ALTLB": "ALTL1"},
}
_SELECT_ONE_VARIANT = "WITH LETTERS T OR U ONLY ONE SHOULD BE SELECTED."
OPTION_SELECTIONS: Mapping[str, OptionSelection] = {
    "IX107A": OptionSelection(
        letter="T",
        cards=frozenset({"014300", "015700", "016300", "016400", "016700", "016800"}),
    ),
    "IX207A": OptionSelection(
        letter="T",
        cards=frozenset(
            {
                "014400",
                "014800",
                "016200",
                "016600",
                "017500",
                "017600",
                "017900",
                "018000",
                "018200",
                "018300",
                "019000",
                "019100",
            }
        ),
    ),
    "IX208A": OptionSelection(
        letter="T",
        cards=frozenset(
            {
                "013800",
                "014300",
                "015800",
                "016300",
                "017300",
                "017600",
                "017800",
                "018100",
            }
        ),
    ),
}
_SWITCH_SETTINGS = {"SWITCH-1": SwitchStatus.ON, "SWITCH-2": SwitchStatus.OFF}
_X_CARD_FILE_RE = re.compile(r"XXXX[XPD](\d{3})")
_HEADER_RE = re.compile(
    r"^.{6}\*HEADER,COBOL,(\w+),(SUBPRG|SUBRTN),(\w+)", re.MULTILINE
)
_SUBPRG = "SUBPRG"
_SUBRTN = "SUBRTN"
NIST_CHECKER_PROPERTY = "nist_checker"
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


def _expanded_content(expanded: str) -> str:
    """The code of expanded source, comment lines dropped. Expanded lines carry no
    sequence or identification area, and a replaced or folded line may run past
    column 72, so nothing after the indicator area is cut."""
    return " ".join(
        line[_TEXT_AREA_START:]
        for line in expanded.splitlines()
        if not (len(line) > 6 and line[6] in ("*", "/"))
    )


def extract_file_controls(expanded: str) -> list[tuple[str, str]]:
    """Return [(cobol_file_name, assign_to), ...] from SELECT...ASSIGN TO clauses."""
    content = _expanded_content(expanded)
    return [
        (m.group(1).upper(), m.group(2).upper())
        for m in _SELECT_ASSIGN_RE.finditer(content)
    ]


def expanded_file_controls(
    parser: ProLeapCobolParser, units: Sequence[str]
) -> list[tuple[str, str]]:
    """The file controls of each unit as the compiler sees it: COPYs inlined with
    their REPLACING applied, so a SELECT in copied text is mapped by the name the
    program gives it."""
    return [
        control
        for unit in units
        for control in extract_file_controls(parser.expand(unit.encode()))
    ]


def _x_card_file(assign_to: str) -> str:
    """The file an ASSIGN names. EXEC85 reads an X-card's number from columns
    17-19 and ignores column 16, so XXXXP001 (passed on) and XXXXD001 (read
    back) are the one file X-card 001 names."""
    return _X_CARD_FILE_RE.sub(r"XXXXX\1", assign_to).lower()


def _is_comment(line: str) -> bool:
    return len(line) > 6 and line[6] == "*"


def _activated(line: str, cards: frozenset[str]) -> str:
    if _is_comment(line) and line[:6] in cards:
        return line[:6] + " " + line[7:]
    return line


def select_option(src: str, prog: str, selection: OptionSelection) -> str:
    """Activate the cards of the selected optional-code variant, as EXEC85's *OPT
    card does. The corpus ships every variant card commented out with its letter
    lost, so the cards are named by sequence number; each must be a comment line,
    and the program must carry the deck's select-exactly-one instruction."""
    lines = src.splitlines()
    commented = sorted(line[:6] for line in lines if _is_comment(line))
    selected = [card for card in commented if card in selection.cards]
    remarks = [_words(c) for c in _comment_lines(src)]
    assert (selected, _SELECT_ONE_VARIANT in remarks) == (
        sorted(selection.cards),
        True,
    ), f"{prog}: not a program offering the {selection.letter} variant it is configured to select"
    return "\n".join(_activated(line, selection.cards) for line in lines)


def programs_offering_variants() -> tuple[str, ...]:
    """The corpus programs whose deck says to select exactly one T or U variant."""
    return tuple(
        path.stem
        for path in sorted(NIST_DIR.glob("*.CBL"))
        if _SELECT_ONE_VARIANT in (_words(c) for c in _comment_lines(path.read_text()))
    )


def _with_option(prog: str, src: str) -> str:
    if prog in OPTION_SELECTIONS:
        return select_option(src, prog, OPTION_SELECTIONS[prog])
    return src


def _source(prog: str) -> str:
    return substitute_x_cards(
        _with_option(prog, (NIST_DIR / f"{prog}.CBL").read_text())
    )


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


_JobLinks = Sequence[tuple[str, str, str]]


def _preceding_in(links: _JobLinks, prog: str) -> list[str]:
    owners = [
        owner for owner, link, member in links if (link, member) == (_SUBPRG, prog)
    ]
    return [
        *owners,
        *(
            member
            for owner, link, member in links
            if link == _SUBPRG and owner in owners and member < prog
        ),
    ]


def preceding_run_units(prog: str) -> list[str]:
    """The run units a SUBPRG member follows in its CCVS job: the owner, then
    each earlier member. They create the files this program reads."""
    return _preceding_in(_links(), prog)


def checking_program_in(links: _JobLinks, prog: str) -> str:
    """The next unit of prog's job that runs it first: it checks the files a
    unit that writes no report passes on. Fails when there is none."""
    checkers = sorted(
        member
        for _, link, member in links
        if link == _SUBPRG and prog in _preceding_in(links, member)
    )
    assert (
        checkers != []
    ), f"{prog}: writes no report, and no later unit of its job checks it"
    return checkers[0]


def checking_program(prog: str) -> str:
    return checking_program_in(_links(), prog)


def _is_job_member(prog: str) -> bool:
    return any((link, member) == (_SUBPRG, prog) for _, link, member in _links())


def _x_card_libraries(tmp_path: Path) -> tuple[CopybookLibrary, ...]:
    """The COBOL libraries X-cards 047 and 048 name, each a directory holding its
    members under the text-names a COPY ... OF library uses: SM207A copies ALTLB
    from both, and the X-048 library's ALTLB is the ALTL1 text."""
    return tuple(
        _library(tmp_path / "libraries" / name.lower(), name, members)
        for name, members in _X_CARD_LIBRARIES.items()
    )


def _library(directory: Path, name: str, members: Mapping[str, str]) -> CopybookLibrary:
    directory.mkdir(parents=True, exist_ok=True)
    for text_name, member in members.items():
        (directory / f"{text_name}.CPY").write_text(
            (NIST_DIR / f"{member}.CPY").read_text()
        )
    return CopybookLibrary(name, directory)


def _run_unit(prog: str, tmp_path: Path, max_steps: int) -> tuple[Path, RunOutcome]:
    """Compile a program with its SUBRTN subprograms, run it, return its print path
    and how the run ended."""
    src = _source(prog)
    callees = [_source(callee) for callee in subroutines(prog)]
    parser = make_cobol_parser(
        copybook_dirs=[NIST_DIR], copybook_libraries=_x_card_libraries(tmp_path)
    )
    provider, print_path = make_provider(
        expanded_file_controls(parser, [src, *callees]),
        tmp_path,
        input_deck(NIST_DIR / f"{prog}.DAT"),
    )
    linked = compile_cobol(
        src.encode(),
        parser=parser,
        programs=tuple(
            SourceFile(Path(f"{callee}.CBL"), text.encode())
            for callee, text in zip(subroutines(prog), callees, strict=True)
        ),
        copybook_dirs=[NIST_DIR],
    )
    label = linked.entry_func_label
    outcome = run_linked_resumable(
        linked,
        entry_point=EntryPoint.function(lambda ref: ref.label == label),
        max_steps=max_steps,
        io_provider=provider,
        builtins=core_builtins(),
        initial_vm=initial_vm_state(io_provider=provider),
        permit_unresolved_call_targets=False,
    )
    return print_path, outcome


def _run_job(prog: str, tmp_path: Path) -> Path:
    for unit in preceding_run_units(prog):
        _run_unit(unit, tmp_path, _MAX_STEPS)[0].unlink(missing_ok=True)
    return run_within_budget(prog, tmp_path, _MAX_STEPS)


def run_nist(
    prog: str, tmp_path: Path, record_property: Callable[[str, str], None]
) -> None:
    """Run a CCVS program as its job does, then assert it passed.

    The run units it follows run first in the same directory, so the files they
    pass on are there; their reports are discarded before this program runs. A
    job member that writes no report takes its checking program's verdict: that
    program's job runs in a directory of its own and must pass, and the checker's
    name is recorded for the report.
    """
    if not (NIST_DIR / f"{prog}.CBL").exists():
        raise NistSkip(NistOutcome.SOURCE_MISSING, f"NIST source not found: {prog}")
    print_path = _run_job(prog, tmp_path)
    if print_path.exists() or not _is_job_member(prog):
        assert_nist_pass(print_path, prog)
        return
    checker = checking_program(prog)
    record_property(NIST_CHECKER_PROPERTY, checker)
    assert_nist_pass(_run_job(checker, tmp_path / checker), checker)


def run_within_budget(prog: str, tmp_path: Path, max_steps: int) -> Path:
    print_path, outcome = _run_unit(prog, tmp_path, max_steps)
    if isinstance(outcome, BudgetExhausted):
        message = (
            f"{prog}: step budget of {max_steps} exhausted before the program ended."
        )
        raise NistFailure(NistOutcome.STEP_BUDGET_EXHAUSTED, message, message)
    return print_path


def run_display_report(
    prog: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> list[str]:
    """Run a CCVS program that DISPLAYs its report instead of writing a PRINT-FILE,
    and return the lines it displayed."""
    capsys.readouterr()
    _run_unit(prog, tmp_path, _MAX_STEPS)
    return capsys.readouterr().out.splitlines()


def make_provider(
    file_controls: Sequence[tuple[str, str]],
    tmp_path: Path,
    system_input: Sequence[str] = (),
) -> tuple[RealFileIOProvider, Path]:
    """Build RealFileIOProvider; return (provider, print_file_path).

    A program with no PRINT file gets a path that is never written.
    """
    overrides = {
        file_name: tmp_path / f"{_x_card_file(assign_to)}.dat"
        for file_name, assign_to in file_controls
    }
    print_path = next(
        (path for file_name, path in overrides.items() if "PRINT" in file_name),
        tmp_path / _NO_PRINT_FILE,
    )
    provider = RealFileIOProvider(
        base_dir=tmp_path,
        inputs=RunInputs(
            file_control=[],
            path_overrides=overrides,
            system_input=system_input,
            switches=_SWITCH_SETTINGS,
        ),
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
    if counts == []:
        message = (
            f"{prog}: completion banner present but no 'TEST(S) FAILED' summary line "
            f"found — cannot confirm a clean run."
        )
        raise NistFailure(NistOutcome.NO_SUMMARY, message, message)
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
        raise NistSkip(
            NistOutcome.NO_PRINT_FILE,
            f"{prog}: PRINT-FILE not written — program did not produce output",
        )

    records = _print_records(print_path.read_bytes())
    text = "\n".join(records)
    _assert_complete(text, len(records), prog)
    _assert_summary_clean(text, prog)
    _assert_no_inline_failures(records, prog)


def _assert_complete(text: str, record_count: int, prog: str) -> None:
    if _END_OF_TEST not in text:
        message = (
            f"{prog}: did not run to completion — '{_END_OF_TEST}' banner absent "
            f"({record_count} record(s) written). Program halted before its summary."
        )
        raise NistFailure(NistOutcome.INCOMPLETE, message, message)


def _assert_summary_clean(text: str, prog: str) -> None:
    n_failed = _summary_failed_count(text, prog)
    if n_failed != 0:
        message = f"{prog}: CCVS summary reports {n_failed} failed test(s)."
        raise NistFailure(NistOutcome.SUMMARY_FAILURES, message, message)


def _assert_no_inline_failures(records: Sequence[str], prog: str) -> None:
    inline_fails = [r for r in records if "FAIL*" in r]
    if inline_fails != []:
        raise NistFailure(
            NistOutcome.INLINE_FAILURES,
            f"{prog}: inline FAIL* records:\n" + "\n".join(inline_fails),
            inline_fails[0].strip(),
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
        raise NistSkip(NistOutcome.SOURCE_MISSING, f"NIST source not found: {src_path}")
    comments = _comment_lines(src_path.read_text())
    totals = [int(m[1]) for c in comments if (m := _FLAGS_EXPECTED_RE.search(c))]
    assert (header in comments, totals) == (
        True,
        [flags_expected],
    ), f"{prog}: not the flagger program it is classified as"
    raise NistSkip(
        NistOutcome.FIPS_FLAGGER,
        f"{prog}: FIPS flagger test (program header: '{header}'; "
        f"'TOTAL NUMBER OF FLAGS EXPECTED = {flags_expected}.') -- its verdict is "
        f"compile-time flagging messages, not run-time output; red-dragon has no "
        f"FIPS flagger",
    )


def _words(text: str) -> str:
    return " ".join(text.split())


def _code_lines(src: str) -> list[str]:
    return [
        _words(line[_TEXT_AREA_START:_TEXT_AREA_END])
        for line in src.splitlines()
        if len(line) > 6 and line[6] != "*" and line[_TEXT_AREA_START:].strip()
    ]


def exit_nested_under(src: str, reel_test: str, exit_test: str) -> bool:
    """Whether ``IF exit_test`` is the very next code after an ``IF reel_test``
    that no period ends: the comment lines between them took the period with
    them, so the second IF is the first one's statement."""
    code = _code_lines(src)
    return any(
        line == f"IF {_words(reel_test)}"
        and following.startswith(f"IF {_words(exit_test)}")
        for line, following in itertools.pairwise(code)
    )


def skip_reel_lines_deleted(
    prog: str, deleted_remark: str, reel_test: str, exit_test: str
) -> None:
    """Classify a CCVS multi-reel/unit program whose deck ships its reel/unit
    lines commented out, and skip it with a reason quoting them.

    The deck's own remark (MOVE "CLOSE REEL DELETED" TO RE-MARK, itself
    commented out) marks the deletion. The deleted lines carried the period that
    ended ``IF reel_test``, so ``IF exit_test`` -- the write loop's only exit --
    is nested under it and needs both conditions at once: the program as
    distributed never ends on any conforming compiler. Both facts are checked
    against the source, so the classification cannot drift.
    """
    src_path = NIST_DIR / f"{prog}.CBL"
    if not src_path.exists():
        raise NistSkip(NistOutcome.SOURCE_MISSING, f"NIST source not found: {src_path}")
    src = src_path.read_text()
    remarks = [_words(c) for c in _comment_lines(src)]
    assert (
        _words(deleted_remark) in remarks,
        exit_nested_under(src, reel_test, exit_test),
    ) == (True, True), f"{prog}: not the reel-lines-deleted program it is classified as"
    raise NistSkip(
        NistOutcome.REEL_LINES_DELETED,
        f"{prog}: its deck comments out the reel/unit lines ('{_words(deleted_remark)}'), "
        f"which took the period ending 'IF {reel_test}' with them, so 'IF {exit_test}', "
        f"the write loop's only exit, is nested under it and can never be reached; "
        f"as distributed the program does not terminate",
    )


_NIST_RESULT_PROPERTY = "nist_result"


def _recorded(report: pytest.TestReport) -> bool:
    return report.when == "call" or (report.when == "setup" and not report.passed)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Function, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if _recorded(report):
        checkers = tuple(
            str(value)
            for name, value in item.user_properties
            if name == NIST_CHECKER_PROPERTY
        )
        result = nist_result(str(item.callspec.params["prog"]), call, checkers)
        report.user_properties = [
            *report.user_properties,
            (_NIST_RESULT_PROPERTY, result.model_dump_json()),
        ]
    return report
