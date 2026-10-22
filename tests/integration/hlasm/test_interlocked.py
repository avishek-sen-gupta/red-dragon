# pyright: standard
"""Interlocked-update instructions run on the VM leave the Principles of Operation registers, storage and CC, or abend S0C6 for an operand off its boundary or an unassigned code, with storage unchanged."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import interlocked_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine, run_hlasm_storage
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")
SECTION = "T"


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


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", sorted(programs.ABENDS))
def test_a_specification_exception_leaves_storage_unchanged(case: str):
    body = programs.CASES[case][0]
    untouched = run_hlasm_storage(
        programs.interlocked_program(""), SECTION, programs.DATA_SPAN
    )[1]
    machine, image = run_hlasm_storage(
        programs.interlocked_program(body), SECTION, programs.DATA_SPAN
    )

    assert (machine.run, image) == (SPECIFICATION, untouched)
