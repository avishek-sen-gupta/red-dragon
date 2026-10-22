# pyright: standard
"""BFP arithmetic instructions run on the VM: every mnemonic's result images, CC and FPC flags, and each IEEE trap's delivered value, DXC and S0C7."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import bfp_arithmetic_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_float, run_hlasm_fpc


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_bfp_instruction_leaves_the_registers_cc_and_fpc(case: str):
    body, registers = programs.CASES[case][:2]
    machine, left = run_hlasm_fpc(programs.program(body))

    assert (machine.restricted_to(registers), left) == (
        programs.expected(case),
        programs.CASES[case][4],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.TRAPS))
def test_ieee_trap_delivers_or_suppresses_then_abends_with_the_dxc(case: str):
    body, fprs = programs.TRAPS[case][:2]
    machine, left, fpc = run_hlasm_float(programs.program(body))

    assert (machine.run, machine.cc, {r: left[r] for r in fprs}, fpc) == (
        programs.expected_trap(case)
    )
