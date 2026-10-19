"""A job member that writes no report is checked by the next unit of its job that runs it first."""

from __future__ import annotations

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.nist.conftest import checking_program, checking_program_in

_JOB = (
    ("XX101A", "SUBPRG", "XX102A"),
    ("XX101A", "SUBPRG", "XX103A"),
    ("XX101A", "SUBPRG", "XX104A"),
    ("XX101A", "SUBRTN", "XX105A"),
    ("XX201A", "SUBPRG", "XX202A"),
)


def _refusal(prog: str) -> str:
    with pytest.raises(AssertionError) as refused:
        checking_program_in(_JOB, prog)
    return str(refused.value).splitlines()[0]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_checker_is_the_next_job_member_that_runs_the_unit_first() -> None:
    assert (
        [checking_program_in(_JOB, prog) for prog in ("XX102A", "XX103A", "XX201A")],
        [_refusal(prog) for prog in ("XX104A", "XX202A")],
    ) == (
        ["XX103A", "XX104A", "XX202A"],
        [
            "XX104A: writes no report, and no later unit of its job checks it",
            "XX202A: writes no report, and no later unit of its job checks it",
        ],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_corpus_pairs_each_sort_unit_with_the_unit_after_it() -> None:
    units = ("ST102A", "ST110A", "ST113M", "ST116A", "ST120A", "ST123A")
    assert {unit: checking_program(unit) for unit in units} == {
        "ST102A": "ST103A",
        "ST110A": "ST111A",
        "ST113M": "ST114M",
        "ST116A": "ST117A",
        "ST120A": "ST121A",
        "ST123A": "ST124A",
    }
