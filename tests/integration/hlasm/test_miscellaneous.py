# pyright: standard
"""Miscellaneous and access-register instructions run on the VM leave the Principles of Operation registers, CC and abend; a check that abends stores nothing; a program-mask bit set by SPM turns a signed overflow into S0C8."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import miscellaneous_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine, run_hlasm_storage

SECTION = "T"
UNTOUCHED_OUT = bytes([0xFF]) * 64
CHECKED_STORES = ("STAM off a word", "STFLE off a doubleword")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_miscellaneous_instruction_leaves_the_registers_cc_and_abend(case: str):
    body, registers = programs.CASES[case][:2]
    machine = run_hlasm_machine(programs.program(body))

    assert machine.restricted_to(registers) == programs.expected(case)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", CHECKED_STORES)
def test_a_boundary_abend_stores_nothing(case: str):
    body = programs.CASES[case][0]
    machine, out = run_hlasm_storage(programs.program(body), SECTION, programs.OUT_SPAN)

    assert (machine.run, out) == (programs.expected(case).run, UNTOUCHED_OUT)
