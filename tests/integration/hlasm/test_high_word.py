# pyright: standard
"""High-word instructions run on the VM change only bits 0-31 of R1, read the high or low word of each operand the Principles of Operation name, and set or keep the CC."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import high_word_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_high_word_instruction_leaves_the_registers_and_cc(case: str):
    body, registers = programs.CASES[case][:2]
    machine = run_hlasm_machine(storage.based_program(body, storage.ABEND))

    assert machine.restricted_to(registers) == programs.expected(case)
