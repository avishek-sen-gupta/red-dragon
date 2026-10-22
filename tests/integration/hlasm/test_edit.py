# pyright: standard
"""ED and EDMK run on the VM give Principles of Operation results: zoned digits, fill and message bytes by the significance indicator, CC from the last field, GR1 marking for EDMK, and S0C7 with nothing stored."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import edit_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine, run_hlasm_storage
from tests.integration.hlasm.hlasm_machine import HlasmMachine

SECTION = "T"


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.ALL_CASES))
def test_edit_leaves_the_result_cc_and_abend(case: str):
    (body, results, cc), run = programs.ALL_CASES[case]
    machine = run_hlasm_machine(programs.edit_program(body))

    assert machine.restricted_to(results) == HlasmMachine(run, cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.STORAGE_AFTER_ABEND))
def test_an_invalid_digit_leaves_the_pattern_untouched(case: str):
    (body, _, cc), run = programs.ALL_CASES[case]
    span, expected = programs.STORAGE_AFTER_ABEND[case]
    machine, image = run_hlasm_storage(programs.edit_program(body), SECTION, span)

    assert (machine.run, machine.cc, image) == (run, cc, expected)
