# pyright: standard
"""High-word programs leave the same declared registers, CC and abend in RedDragon and in z390, bar z390's load-and-trap abend code and its carry CC for ALSIH with a negative immediate."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import high_word_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

Z390_DXC_AS_INTERRUPTION_CODE = HlasmRun(return_code=0, abend="S0FF", stdout="")
LOAD_HIGH_AND_TRAP_ZERO = "LFHAT zero"
Z390_BORROW_AS_CARRY_CC = {"ALSIH negative": 0, "ALSIH negative borrow": 3}
AGREED = [
    case
    for case in programs.CASES
    if case != LOAD_HIGH_AND_TRAP_ZERO and case not in Z390_BORROW_AS_CARRY_CC
]


def _both(
    z390: Z390Runner, tmp_path: Path, case: str
) -> tuple[HlasmMachine, HlasmMachine]:
    body, registers = programs.CASES[case][:2]
    source = storage.based_program(body, storage.ABEND)
    return (
        run_hlasm_machine(source).restricted_to(registers),
        z390.run_machine(source, tmp_path).restricted_to(registers),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", AGREED)
def test_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    assert _both(z390, tmp_path, case) == (
        programs.expected(case),
        programs.expected(case),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lfhat_of_zero_abends_s0c7_here_and_s0ff_in_z390(
    z390: Z390Runner, tmp_path: Path
):
    here = programs.expected(LOAD_HIGH_AND_TRAP_ZERO)

    assert _both(z390, tmp_path, LOAD_HIGH_AND_TRAP_ZERO) == (
        here,
        HlasmMachine(Z390_DXC_AS_INTERRUPTION_CODE, here.cc, here.gprs),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_BORROW_AS_CARRY_CC))
def test_alsih_negative_sets_the_principles_of_operation_cc_where_z390_reports_borrow_as_carry(
    z390: Z390Runner, tmp_path: Path, case: str
):
    here = programs.expected(case)

    assert _both(z390, tmp_path, case) == (
        here,
        HlasmMachine(here.run, Z390_BORROW_AS_CARRY_CC[case], here.gprs),
    )
