# pyright: standard
"""HFP arithmetic instructions run on the VM: every mnemonic's result images and CC, and each program-mask exception's stored or suppressed result and abend."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import hfp_arithmetic_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_float, run_hlasm_machine


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_hfp_instruction_leaves_the_registers_and_cc(case: str):
    body, registers = programs.CASES[case][:2]
    machine = run_hlasm_machine(programs.program(body))

    assert machine.restricted_to(registers) == programs.expected(case)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.TRAPS))
def test_hfp_exception_stores_or_suppresses_then_abends(case: str):
    body, fprs = programs.TRAPS[case][:2]
    machine, fpr_images, _ = run_hlasm_float(programs.program(body))

    assert (machine.run, machine.cc, {r: fpr_images[r] for r in fprs}) == (
        programs.expected_trap(case)
    )
