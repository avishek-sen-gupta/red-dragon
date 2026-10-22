# pyright: standard
"""z390 does not execute PLO (it abends S0C1 for every function code), so a representative case per PLO operation shape checks RedDragon against the Principles of Operation expectation and pins z390's operation exception."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import perform_locked_operation_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.test_perform_locked_operation import expected_run
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")

REPRESENTATIVE = (
    "PLO 0 all equal",
    "PLO 4 all equal",
    "PLO 9 unequal at compare 2",
    "PLO 13 all equal",
    "PLO 21 all equal",
    "PLO 26 all equal",
    "PLO 31 unequal at compare 2",
    "PLO 36 all equal",
    "PLO 44",
    "PLO 57",
    "PLO test bit, code 62",
    "PLO code 62",
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", REPRESENTATIVE)
def test_follows_the_principles_of_operation_where_z390_does_not_execute_plo(
    z390: Z390Runner, tmp_path: Path, case: str
):
    program, results, cc, _ = programs.CASES[case]

    assert (
        run_hlasm_machine(program).restricted_to(results),
        z390.run_machine(program, tmp_path).run,
    ) == (HlasmMachine(expected_run(case), cc, results), OPERATION)
