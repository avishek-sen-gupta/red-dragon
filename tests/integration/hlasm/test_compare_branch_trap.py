# pyright: standard
"""Compare-and-branch, compare-and-trap and load-and-trap instructions run on the VM take the path or trap M3 selects, abend S0C7 on a trap with the register already loaded, and leave the CC unchanged."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import compare_branch_trap_programs as programs
from tests.integration.hlasm.branch_on_condition_programs import path_program
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_compare_and_branch_or_trap_follows_m3_and_keeps_the_cc(case: str):
    cc, body, registers, _ = programs.CASES[case]
    machine = run_hlasm_machine(path_program(cc, body))

    assert machine.restricted_to(registers) == programs.expected(case)
