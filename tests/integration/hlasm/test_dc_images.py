# pyright: standard
"""DC constants assembled into a section hold their HLASM images when the program loads them; bit-length forms z390 misassembles follow the Language Reference's bit-length modifier rules (fields from the next free bit, C from its high-order end, others from the low-order end, the last byte zero-filled)."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import dc_image_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("family", list(programs.FAMILIES))
def test_constants_hold_their_images(family: str):
    constants, image = programs.FAMILIES[family]
    expected = programs.registers(image)
    source = programs.image_program(constants, len(expected))

    assert run_hlasm_machine(source).restricted_to(expected) == HlasmMachine(
        ABENDED, 0, expected
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_alignment_inside_a_statement_is_zero_filled():
    expected = programs.registers(programs.PADDING_IMAGE)
    source = programs.image_program(programs.PADDING, len(expected))

    assert run_hlasm_machine(source).restricted_to(expected) == HlasmMachine(
        ABENDED, 0, expected
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bit_length_forms_follow_the_language_reference():
    expected = programs.registers(programs.BIT_LENGTHS_PAST_Z390_IMAGE)
    source = programs.image_program(programs.BIT_LENGTHS_PAST_Z390, len(expected))

    assert run_hlasm_machine(source).restricted_to(expected) == HlasmMachine(
        ABENDED, 0, expected
    )
