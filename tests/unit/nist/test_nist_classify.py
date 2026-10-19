"""A NIST test's outcome is read from the type of what it raised, never its text."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.nist.nist_classify import nist_result
from tests.nist.nist_failure import NistFailure
from tests.nist.nist_outcome import NistOutcome
from tests.nist.nist_result import NistResult
from tests.nist.nist_skip import NistSkip
from tests.nist.nist_verdict import NistVerdict


def _passes() -> None:
    pass


def _raising(exc: BaseException) -> Callable[[], None]:
    def run() -> None:
        raise exc

    return run


def _result(run: Callable[[], None]) -> NistResult:
    call = pytest.CallInfo[None].from_call(run, "call")
    return nist_result("NC101A", call)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_raised_type_maps_to_one_outcome() -> None:
    results = [
        _result(_passes),
        _result(
            _raising(
                NistFailure(
                    NistOutcome.INLINE_FAILURES,
                    "NC101A: inline FAIL* records:\nFAIL* ADD-TEST-1",
                    "FAIL* ADD-TEST-1",
                )
            )
        ),
        _result(_raising(NistSkip(NistOutcome.NO_PRINT_FILE, "NC101A: no file\nx"))),
        _result(_raising(pytest.skip.Exception("needs an MCS"))),
        _result(_raising(ValueError("bad picture\nsecond line"))),
        _result(_raising(AssertionError("X-card overflows"))),
    ]

    assert [(r.program, r.outcome, r.detail) for r in results] == [
        ("NC101A", NistOutcome.PASS, ""),
        ("NC101A", NistOutcome.INLINE_FAILURES, "FAIL* ADD-TEST-1"),
        ("NC101A", NistOutcome.NO_PRINT_FILE, "NC101A: no file"),
        ("NC101A", NistOutcome.UNSUPPORTED, "needs an MCS"),
        ("NC101A", NistOutcome.ERROR, "ValueError: bad picture"),
        ("NC101A", NistOutcome.ERROR, "AssertionError: X-card overflows"),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_outcome_has_the_verdict_pytest_gives_it() -> None:
    assert {o: o.verdict for o in NistOutcome} == {
        NistOutcome.PASS: NistVerdict.PASS,
        NistOutcome.INCOMPLETE: NistVerdict.FAIL,
        NistOutcome.SUMMARY_FAILURES: NistVerdict.FAIL,
        NistOutcome.INLINE_FAILURES: NistVerdict.FAIL,
        NistOutcome.NO_SUMMARY: NistVerdict.FAIL,
        NistOutcome.STEP_BUDGET_EXHAUSTED: NistVerdict.FAIL,
        NistOutcome.ERROR: NistVerdict.FAIL,
        NistOutcome.FIPS_FLAGGER: NistVerdict.SKIP,
        NistOutcome.REEL_LINES_DELETED: NistVerdict.SKIP,
        NistOutcome.NO_PRINT_FILE: NistVerdict.SKIP,
        NistOutcome.SOURCE_MISSING: NistVerdict.SKIP,
        NistOutcome.UNSUPPORTED: NistVerdict.SKIP,
    }
    assert (
        isinstance(NistFailure(NistOutcome.INCOMPLETE, "m", "m"), AssertionError),
        isinstance(NistSkip(NistOutcome.SOURCE_MISSING, "m"), pytest.skip.Exception),
    ) == (True, True)
