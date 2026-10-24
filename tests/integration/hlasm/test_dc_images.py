# pyright: standard
"""DC constants assembled into a section hold their HLASM images when the program loads them. Forms z390 misassembles or cannot assemble follow the Language Reference (SC26-4940-09): bit-length modifiers (pp. 125-126: fields from the next free bit, C, E, D and L from their high-order end, others from the low-order end, the last byte zero-filled); without a type extension an HFP zero is positive, and scale shifts the fraction right (pp. 127, 153); EE2'.46415' is 46.415 (p. 153); a length modifier rounds the fraction (p. 150); H overflows to the largest magnitude and denormalizes (p. 151); BFP converts correctly rounded under its rounding mode (pp. 156-157); special values (p. 158); DFP keeps the written quantum (IEEE 754-2008 conversion, not stated by the manual), and DFP (MIN) is the smallest normal number (our reading: p. 158 states MIN only for BFP and HFP)."""

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
@pytest.mark.parametrize("family", list(programs.PAST_Z390))
def test_forms_z390_misassembles_follow_the_language_reference(family: str):
    constants, image = programs.PAST_Z390[family]
    expected = programs.registers(image)
    source = programs.image_program(constants, len(expected))

    assert run_hlasm_machine(source).restricted_to(expected) == HlasmMachine(
        ABENDED, 0, expected
    )
