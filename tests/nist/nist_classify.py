"""Maps what a NIST test raised to its outcome, by the raised type alone."""

from __future__ import annotations

import pytest

from tests.nist.nist_failure import NistFailure
from tests.nist.nist_outcome import NistOutcome
from tests.nist.nist_result import NistResult
from tests.nist.nist_skip import NistSkip


def _first_line(exc: BaseException) -> str:
    return next(iter(str(exc).splitlines()), "")


def _classified(exc: BaseException) -> tuple[NistOutcome, str]:
    match exc:
        case NistFailure() | NistSkip():
            return exc.outcome, exc.detail
        case pytest.skip.Exception():
            return NistOutcome.UNSUPPORTED, _first_line(exc)
        case _:
            return NistOutcome.ERROR, f"{type(exc).__name__}: {_first_line(exc)}"


def nist_result(program: str, call: pytest.CallInfo[None]) -> NistResult:
    match call.excinfo:
        case None:
            return NistResult(program=program, outcome=NistOutcome.PASS, detail="")
        case excinfo:
            outcome, detail = _classified(excinfo.value)
            return NistResult(program=program, outcome=outcome, detail=detail)
