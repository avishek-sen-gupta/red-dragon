# pyright: standard
"""Unicode conversion and string search programs run on the VM leave the Principles of Operation storage, registers and CC, and abend S0C6 on a specification exception with storage unchanged."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import unicode_string_search_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine, run_hlasm_storage
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
def test_specification_exception_abends_s0c6_and_changes_nothing(case: str):
    body, results, cc = programs.SPECIFICATION_EXCEPTIONS[case]
    untouched = run_hlasm_storage(
        programs.unicode_program(""), programs.SECTION, programs.DATA_SPAN
    )[1]
    machine, image = run_hlasm_storage(
        programs.unicode_program(body), programs.SECTION, programs.DATA_SPAN
    )

    assert (machine.restricted_to(results), image) == (
        HlasmMachine(SPECIFICATION, cc, results),
        untouched,
    )
