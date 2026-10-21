# pyright: standard
"""Branch on condition instructions run on the VM take the path the mask selects for the CC and leave the CC unchanged."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import branch_on_condition_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm, run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")


def _path(taken: bool) -> int:
    return programs.TAKEN if taken else programs.FELL_THROUGH


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_branch_takes_the_path_the_mask_selects(case: str):
    cc, branch, taken = programs.CASES[case]
    machine = run_hlasm_machine(programs.path_program(cc, branch))

    assert machine.restricted_to((programs.PATH_REGISTER,)) == HlasmMachine(
        ABENDED, cc, {programs.PATH_REGISTER: _path(taken)}
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_branch_targets_resolve_through_the_dispatch():
    machine = run_hlasm_machine(programs.cross_section_program())

    assert machine.restricted_to((programs.PATH_REGISTER,)) == HlasmMachine(
        ABENDED, 1, {programs.PATH_REGISTER: programs.TAKEN}
    )
    assert [
        run_hlasm(programs.path_program(0, branch)) for branch in programs.INTO_DATA
    ] == [OPERATION] * len(programs.INTO_DATA)
