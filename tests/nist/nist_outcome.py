"""Why a NIST program's test reached its verdict."""

from __future__ import annotations

from enum import Enum

from tests.nist.nist_verdict import NistVerdict


class NistOutcome(Enum):
    """Why a NIST program's test reached its verdict."""

    PASS = "pass"
    INCOMPLETE = "incomplete"
    SUMMARY_FAILURES = "summary-failures"
    INLINE_FAILURES = "inline-failures"
    NO_SUMMARY = "no-summary"
    STEP_BUDGET_EXHAUSTED = "step-budget-exhausted"
    ERROR = "error"
    FIPS_FLAGGER = "fips-flagger"
    NO_PRINT_FILE = "no-print-file"
    SOURCE_MISSING = "source-missing"
    UNSUPPORTED = "unsupported"

    @property
    def verdict(self) -> NistVerdict:
        return _VERDICTS[self]


_VERDICTS = {
    NistOutcome.PASS: NistVerdict.PASS,
    NistOutcome.INCOMPLETE: NistVerdict.FAIL,
    NistOutcome.SUMMARY_FAILURES: NistVerdict.FAIL,
    NistOutcome.INLINE_FAILURES: NistVerdict.FAIL,
    NistOutcome.NO_SUMMARY: NistVerdict.FAIL,
    NistOutcome.STEP_BUDGET_EXHAUSTED: NistVerdict.FAIL,
    NistOutcome.ERROR: NistVerdict.FAIL,
    NistOutcome.FIPS_FLAGGER: NistVerdict.SKIP,
    NistOutcome.NO_PRINT_FILE: NistVerdict.SKIP,
    NistOutcome.SOURCE_MISSING: NistVerdict.SKIP,
    NistOutcome.UNSUPPORTED: NistVerdict.SKIP,
}
