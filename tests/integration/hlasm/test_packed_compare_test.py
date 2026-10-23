# pyright: standard
"""CP and TP run on the VM set the Principles of Operation CC: CP by algebraic value, -0 equal to +0, abending S0C7 with the CC unchanged on an invalid code; TP by which of the digits and sign are valid; neither changes storage."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import packed_compare_test_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine, run_hlasm_storage
from tests.integration.hlasm.hlasm_machine import HlasmMachine


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.ALL_CASES))
def test_packed_compare_and_test_leave_the_cc_or_abend(case: str):
    (body, cc), run = programs.ALL_CASES[case]
    machine = run_hlasm_machine(programs.compare_test_program(body))

    assert machine.restricted_to(()) == HlasmMachine(run, cc, {})


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.ALL_CASES))
def test_packed_compare_and_test_leave_their_operands_unchanged(case: str):
    body = programs.ALL_CASES[case][0][0]
    untouched = run_hlasm_storage(
        programs.compare_test_program(""), programs.SECTION, programs.DATA_SPAN
    )[1]
    image = run_hlasm_storage(
        programs.compare_test_program(body), programs.SECTION, programs.DATA_SPAN
    )[1]

    assert image == untouched
