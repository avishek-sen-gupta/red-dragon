# pyright: standard
"""Signed add and subtract instructions run on the VM leave the Principles of Operation result and CC, overflow included."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm import signed_add_subtract_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("mnemonic", list(programs.CASES))
def test_signed_add_or_subtract_sets_the_result_and_cc(mnemonic: str):
    body, results, cc = programs.CASES[mnemonic]
    machine = run_hlasm_machine(storage.based_program(body, storage.ABEND))

    assert machine.restricted_to(results) == HlasmMachine(ABENDED, cc, results)
