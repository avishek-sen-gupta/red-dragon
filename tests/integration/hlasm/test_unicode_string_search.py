# pyright: standard
"""Unicode conversion and string search programs run on the VM leave the Principles of Operation storage, registers and CC, and a search abends S0C6 on a specification exception before writing a register."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import unicode_string_search_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_unicode_string_search_leaves_storage_registers_and_cc(case: str):
    body, results, cc = programs.CASES[case]
    machine = run_hlasm_machine(programs.unicode_program(body))

    assert machine.restricted_to(results) == HlasmMachine(ABENDED, cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.SPECIFICATION_EXCEPTIONS))
def test_search_specification_exception_abends_s0c6_before_writing_a_register(
    case: str,
):
    body, results, cc = programs.SPECIFICATION_EXCEPTIONS[case]
    machine = run_hlasm_machine(programs.unicode_program(body))

    assert machine.restricted_to(results) == HlasmMachine(SPECIFICATION, cc, results)
