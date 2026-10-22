# pyright: standard
"""PLO run on the VM: every function code with all compares equal and with each compare missed leaves the Principles of Operation registers, operand and parameter-list storage, unequal-results byte and CC; the test bit, GR0 checks, odd registers and misaligned operands abend S0C6 with storage untouched."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import perform_locked_operation_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_storage
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")
SECTION = "T"


def expected_run(case: str) -> HlasmRun:
    return SPECIFICATION if case in programs.ABENDS else ABENDED


def _stored(image: bytes, storage: programs.Storage) -> programs.Storage:
    start = programs.DATA_SPAN[0]
    return tuple(
        (at, image[at - start : at - start + len(expected)]) for at, expected in storage
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_perform_locked_operation_sets_the_registers_storage_and_cc(case: str):
    program, results, cc, storage = programs.CASES[case]
    machine, image = run_hlasm_storage(program, SECTION, programs.DATA_SPAN)

    assert (machine.restricted_to(results), _stored(image, storage)) == (
        HlasmMachine(expected_run(case), cc, results),
        storage,
    )
