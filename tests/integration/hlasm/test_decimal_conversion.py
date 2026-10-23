# pyright: standard
"""Decimal conversions run on the VM give Principles of Operation results: CVB completes into the low word before S0C9 and CVBG is suppressed, CVD never makes a negative zero, PACK and UNPK process right to left byte by byte, and UNPKA and UNPKU set the CC from the sign."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import decimal_conversion_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine, run_hlasm_storage
from tests.integration.hlasm.hlasm_machine import HlasmMachine


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.ALL_CASES))
def test_decimal_conversion_leaves_the_result_cc_and_abend(case: str):
    (body, results, cc), run = programs.ALL_CASES[case]
    machine = run_hlasm_machine(programs.conversion_program(body))

    assert machine.restricted_to(results) == HlasmMachine(run, cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.SPECIFICATIONS))
def test_a_specification_exception_stores_nothing(case: str):
    body = programs.SPECIFICATIONS[case][0]
    machine, image = run_hlasm_storage(
        programs.conversion_program(body), programs.SECTION, programs.OUT_SPAN
    )

    assert (machine.run, image) == (
        programs.SPECIFICATION,
        bytes([0xFF]) * (programs.OUT_SPAN[1] - programs.OUT_SPAN[0]),
    )
