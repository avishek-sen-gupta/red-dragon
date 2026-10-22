# pyright: standard
"""Interlocked-update instructions run on the VM leave the Principles of Operation registers, storage and CC, or abend S0C6 for an operand off its boundary or an unassigned code."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import interlocked_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")


def expected_run(case: str) -> HlasmRun:
    return SPECIFICATION if case in programs.ABENDS else ABENDED


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_interlocked_update_sets_the_registers_storage_and_cc(case: str):
    body, results, cc = programs.CASES[case]
    machine = run_hlasm_machine(programs.interlocked_program(body))

    assert machine.restricted_to(results) == HlasmMachine(
        expected_run(case), cc, results
    )
