# pyright: standard
"""Multiply and divide instructions run on the VM leave the Principles of Operation products, quotients, remainders and CC, and abend S0C9 on a divide exception."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm import multiply_divide_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
FIXED_POINT_DIVIDE = HlasmRun(return_code=0, abend="S0C9", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("mnemonic", list(programs.CASES))
def test_multiply_or_divide_sets_the_result_and_cc(mnemonic: str):
    body, results, cc = programs.CASES[mnemonic]
    machine = run_hlasm_machine(storage.based_program(body, storage.ABEND))

    assert machine.restricted_to(results) == HlasmMachine(ABENDED, cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.DIVIDE_EXCEPTIONS))
def test_divide_exception_abends_s0c9_and_leaves_the_registers(case: str):
    body, results, cc = programs.DIVIDE_EXCEPTIONS[case]
    machine = run_hlasm_machine(storage.based_program(body, storage.ABEND))

    assert machine.restricted_to(results) == HlasmMachine(
        FIXED_POINT_DIVIDE, cc, results
    )
