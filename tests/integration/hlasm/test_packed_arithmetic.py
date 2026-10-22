# pyright: standard
"""Packed-decimal arithmetic run on the VM stores Principles of Operation results, CCs and abends: S0C6, S0C7 and S0CB before any store, S0CA after it."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import packed_arithmetic_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine, run_hlasm_storage
from tests.integration.hlasm.hlasm_machine import HlasmMachine

SECTION = "T"


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.ALL_CASES))
def test_packed_arithmetic_leaves_the_result_cc_and_abend(case: str):
    (body, results, cc), run = programs.ALL_CASES[case]
    machine = run_hlasm_machine(programs.packed_program(body))

    assert machine.restricted_to(results) == HlasmMachine(run, cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.STORAGE_AFTER_ABEND))
def test_an_abend_leaves_the_overflowed_result_or_the_untouched_operand(case: str):
    (body, _, cc), run = programs.ALL_CASES[case]
    span, expected = programs.STORAGE_AFTER_ABEND[case]
    machine, image = run_hlasm_storage(programs.packed_program(body), SECTION, span)

    assert (machine.run, machine.cc, image) == (run, cc, expected)
