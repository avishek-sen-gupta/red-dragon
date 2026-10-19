"""Renders NIST program results as a module table, categories and failure lines."""

from __future__ import annotations

from collections.abc import Sequence

from tests.nist.nist_module import NistModule
from tests.nist.nist_outcome import NistOutcome
from tests.nist.nist_result import NistResult
from tests.nist.nist_verdict import NistVerdict

_TITLE = "# NIST CCVS conformance report"
_TABLE_HEADER = (
    "| Module | Pass | Fail | Skip | Total | Pass % |\n|---|---:|---:|---:|---:|---:|"
)
_OVERALL = "Overall"
_VERDICT_COLUMNS = (NistVerdict.PASS, NistVerdict.FAIL, NistVerdict.SKIP)


def _row(label: str, results: Sequence[NistResult]) -> str:
    counts = [
        sum(1 for r in results if r.outcome.verdict is verdict)
        for verdict in _VERDICT_COLUMNS
    ]
    cells = [label, *map(str, counts), str(len(results))]
    return f"| {' | '.join(cells)} | {100 * counts[0] / len(results):.1f} |"


def _module_table(results: Sequence[NistResult]) -> str:
    rows = [
        _row(module.value, [r for r in results if r.module is module])
        for module in NistModule
        if any(r.module is module for r in results)
    ]
    return "\n".join([_TABLE_HEADER, *rows, _row(_OVERALL, results)])


def _programs(outcome: NistOutcome, results: Sequence[NistResult]) -> list[str]:
    return sorted(r.program for r in results if r.outcome is outcome)


def _entry(result: NistResult) -> str:
    if result.outcome is NistOutcome.VERIFIED_BY_CHECKER:
        return f"{result.program} ({result.detail})"
    return result.program


def _entries(outcome: NistOutcome, results: Sequence[NistResult]) -> list[str]:
    return [
        _entry(r)
        for r in sorted(results, key=lambda r: r.program)
        if r.outcome is outcome
    ]


def _present(results: Sequence[NistResult]) -> list[NistOutcome]:
    return [o for o in NistOutcome if any(r.outcome is o for r in results)]


def _category(outcome: NistOutcome, results: Sequence[NistResult]) -> str:
    entries = _entries(outcome, results)
    return f"### {outcome.value} ({len(entries)})\n\n{', '.join(entries)}"


def _failure_lines(results: Sequence[NistResult]) -> list[str]:
    return [
        f"- {r.program} ({r.outcome.value}): {r.detail}"
        for r in sorted(results, key=lambda r: r.program)
        if r.outcome.verdict is NistVerdict.FAIL
    ]


def report_markdown(results: Sequence[NistResult]) -> str:
    return "\n\n".join(
        [
            _TITLE,
            _module_table(results),
            "## Categories",
            *(_category(o, results) for o in _present(results)),
            "## First failure line per program",
            "\n".join(_failure_lines(results)) + "\n",
        ]
    )


def terminal_summary(results: Sequence[NistResult]) -> str:
    counts = [f"{o.value}: {len(_programs(o, results))}" for o in _present(results)]
    return f"{_module_table(results)}\n\n" + "\n".join(counts)
