# pyright: standard
"""Compare-and-branch, compare-and-trap and load-and-trap programs take the same path, trap and CC in RedDragon and in z390, bar z390's load-and-trap abend code and its missing CLT and CLGT."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import compare_branch_trap_programs as programs
from tests.integration.hlasm.branch_on_condition_programs import (
    PATH_REGISTER,
    path_program,
)
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

Z390_DXC_AS_INTERRUPTION_CODE = HlasmRun(return_code=0, abend="S0FF", stdout="")
OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")
LOAD_AND_TRAP_ZERO = ("LAT zero", "LGAT zero", "LLGFAT zero", "LLGTAT bit 0 only")
STORAGE_COMPARE_AND_TRAP = ("CLT", "CLTH", "CLGT", "CLGTNL")
AGREED = [
    case
    for case in programs.CASES
    if case not in (*LOAD_AND_TRAP_ZERO, *STORAGE_COMPARE_AND_TRAP)
]


def _both(
    z390: Z390Runner, tmp_path: Path, case: str
) -> tuple[HlasmMachine, HlasmMachine]:
    cc, body, registers, _ = programs.CASES[case]
    source = path_program(cc, body)
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
@pytest.mark.parametrize("case", LOAD_AND_TRAP_ZERO)
def test_load_and_trap_abends_s0c7_here_and_s0ff_in_z390(
    z390: Z390Runner, tmp_path: Path, case: str
):
    here = programs.expected(case)

    assert _both(z390, tmp_path, case) == (
        here,
        HlasmMachine(Z390_DXC_AS_INTERRUPTION_CODE, here.cc, here.gprs),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", STORAGE_COMPARE_AND_TRAP)
def test_clt_and_clgt_follow_the_principles_of_operation_while_z390_lacks_them(
    z390: Z390Runner, tmp_path: Path, case: str
):
    here = programs.expected(case)

    assert _both(z390, tmp_path, case) == (
        here,
        HlasmMachine(OPERATION, here.cc, {PATH_REGISTER: FILL}),
    )
