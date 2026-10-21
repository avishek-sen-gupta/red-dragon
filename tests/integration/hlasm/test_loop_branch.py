# pyright: standard
"""Branch on count and branch on index run on the VM: loops iterate to their bound, the register overlaps follow the PoO, and the CC is unchanged."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import loop_branch_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")


def _ran(case: programs.LoopCase) -> tuple[HlasmMachine, HlasmMachine]:
    code, registers = case
    machine = run_hlasm_machine(programs.program(code))
    return (
        machine.restricted_to(registers),
        HlasmMachine(ABENDED, programs.PRESET_CC, registers),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.COUNT_CASES))
def test_branch_on_count_decrements_and_branches_while_nonzero(case: str):
    actual, expected = _ran(programs.COUNT_CASES[case])

    assert actual == expected


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.INDEX_CASES))
def test_branch_on_index_steps_the_index_until_it_passes_the_compare_value(case: str):
    actual, expected = _ran(programs.INDEX_CASES[case])

    assert actual == expected


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.OVERLAP_CASES))
def test_branch_on_index_reads_operands_first_and_compares_signed(case: str):
    actual, expected = _ran(programs.OVERLAP_CASES[case])

    assert actual == expected
