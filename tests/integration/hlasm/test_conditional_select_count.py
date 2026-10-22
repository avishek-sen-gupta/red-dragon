# pyright: standard
"""Conditional load and store, select and bit-count instructions run on the VM leave the Principles of Operation registers, storage and CC."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import conditional_select_count_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_conditional_select_or_count_sets_the_result_and_cc(case: str):
    body, results, cc = programs.CASES[case]
    machine = run_hlasm_machine(storage.based_program(body, storage.ABEND))

    assert machine.restricted_to(results) == HlasmMachine(ABENDED, cc, results)
