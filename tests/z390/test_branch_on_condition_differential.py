# pyright: standard
"""Branch on condition programs take the same path and keep the same CC in RedDragon and in z390, bar z390's BIC and its missing BPP and BPRP."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import branch_on_condition_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")
PATH = (programs.PATH_REGISTER,)
Z390_OPERATION_EXCEPTION = frozenset(
    {"BIC", "BI", "BINE", "BIO", "BIH", "BI high word and bit 32", "BPP", "BPRP"}
)
AGREED = [case for case in programs.CASES if case not in Z390_OPERATION_EXCEPTION]


def _expected(case: str) -> HlasmMachine:
    cc, _, taken = programs.CASES[case]
    path = programs.TAKEN if taken else programs.FELL_THROUGH
    return HlasmMachine(ABENDED, cc, {programs.PATH_REGISTER: path})


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", AGREED)
def test_case_matches(z390: Z390Runner, tmp_path: Path, case: str):
    source = programs.path_program(programs.CASES[case][0], programs.CASES[case][1])

    assert (
        run_hlasm_machine(source).restricted_to(PATH),
        z390.run_machine(source, tmp_path).restricted_to(PATH),
    ) == (_expected(case), _expected(case))


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", sorted(Z390_OPERATION_EXCEPTION))
def test_taken_bic_and_branch_prediction_abend_s0c1_in_z390_only(
    z390: Z390Runner, tmp_path: Path, case: str
):
    cc, branch, _ = programs.CASES[case]
    source = programs.path_program(cc, branch)

    assert (
        run_hlasm_machine(source).restricted_to(PATH),
        z390.run_machine(source, tmp_path).restricted_to(PATH),
    ) == (
        _expected(case),
        HlasmMachine(OPERATION, cc, {programs.PATH_REGISTER: FILL}),
    )
