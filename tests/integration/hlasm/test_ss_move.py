# pyright: standard
"""Storage moves run on the VM leave the Principles of Operation storage, registers and CC, overlapping operands included, and abend S0C6 on a specification exception."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import ss_move_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_move_leaves_the_storage_registers_and_cc(case: str):
    body, results, cc = programs.CASES[case]
    machine = run_hlasm_machine(programs.move_program(body))

    assert machine.restricted_to(results) == HlasmMachine(ABENDED, cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.SPECIFICATION_EXCEPTIONS))
def test_specification_exception_abends_s0c6_and_leaves_the_registers(case: str):
    body, results, cc = programs.SPECIFICATION_EXCEPTIONS[case]
    machine = run_hlasm_machine(programs.move_program(body))

    assert machine.restricted_to(results) == HlasmMachine(SPECIFICATION, cc, results)
