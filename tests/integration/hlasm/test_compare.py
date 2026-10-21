# pyright: standard
"""Compare instructions run on the VM set the Principles of Operation CC and leave their operands unchanged."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import compare_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm, run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_compare_sets_the_cc_and_stores_nothing(case: str):
    body, results, cc = programs.CASES[case]
    machine = run_hlasm_machine(storage.based_program(body, storage.ABEND))

    assert machine.restricted_to(results) == HlasmMachine(ABENDED, cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_misaligned_relative_compare_is_a_specification_exception():
    assert [
        run_hlasm(storage.relative_program(body, storage.RETURN))
        for body in programs.MISALIGNED
    ] == [SPECIFICATION] * len(programs.MISALIGNED)
