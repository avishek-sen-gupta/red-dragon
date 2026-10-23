# pyright: standard
"""Conditional load and store, select and bit-count programs leave the same declared registers and CC in RedDragon and in z390, bar the instructions z390 does not execute and its whole-register SELFHR."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import conditional_select_count_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")

NOT_EXECUTED = [
    "LOCFHR",
    "LOCFHRP",
    "LOCFHRM",
    "LOCFHRNZ",
    "LOCFH",
    "LOCFHNP",
    "LOCFHNM",
    "LOCHI",
    "LOCHIH",
    "LOCHINL",
    "LOCGHI",
    "LOCGHIZ",
    "LOCGHINH",
    "LOCHHI",
    "LOCHHINE",
    "LOCHHINO",
    "STOCFH",
    "STOCFHO",
    "STOCFHE",
    *programs.ZERO_COUNTS,
    *programs.BITS_UNDER_MASK,
]
BEFORE_THE_INSTRUCTION: Mapping[str, Mapping[int, int]] = {
    "CTZG in place": {4: programs.SRCP},
    "BEXTG left-justified": {5: programs.SRCP},
    "BDEPG three mask bits": {6: programs.DNEG},
}
SELECT_HIGH_WHOLE_REGISTER: Mapping[str, Mapping[int, int]] = {
    "SELFHR": {4: programs.SRC},
    "SELFHRL": {4: programs.SRCP},
    "SELFHRNE": {4: programs.SRC},
}
AGREED = [
    case
    for case in programs.CASES
    if case not in NOT_EXECUTED and case not in SELECT_HIGH_WHOLE_REGISTER
]


def _both(
    z390: Z390Runner, tmp_path: Path, case: str
) -> tuple[HlasmMachine, HlasmMachine]:
    body, results, _ = programs.CASES[case]
    source = storage.based_program(body, storage.ABEND)
    return (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    )


def _expected(case: str) -> HlasmMachine:
    _, results, cc = programs.CASES[case]
    return HlasmMachine(ABENDED, cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", AGREED)
def test_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    assert _both(z390, tmp_path, case) == (_expected(case), _expected(case))


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", NOT_EXECUTED)
def test_follows_the_principles_of_operation_where_z390_does_not_execute_the_instruction(
    z390: Z390Runner, tmp_path: Path, case: str
):
    here = _expected(case)
    before = {
        **{r: storage.FILL for r in here.gprs},
        **BEFORE_THE_INSTRUCTION.get(case, {}),
    }

    assert _both(z390, tmp_path, case) == (
        here,
        HlasmMachine(OPERATION, here.cc, before),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(SELECT_HIGH_WHOLE_REGISTER))
def test_selfhr_keeps_the_low_word_here_while_z390_selects_the_whole_register(
    z390: Z390Runner, tmp_path: Path, case: str
):
    here = _expected(case)

    assert _both(z390, tmp_path, case) == (
        here,
        HlasmMachine(ABENDED, here.cc, SELECT_HIGH_WHOLE_REGISTER[case]),
    )
