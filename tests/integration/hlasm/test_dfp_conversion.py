# pyright: standard
"""DFP conversion instructions run on the VM: every mnemonic's results, CC and FPC flags, and each trap's delivered value, DXC and S0C7."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import dfp_conversion_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_float, run_hlasm_fpc


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_dfp_conversion_leaves_the_registers_cc_and_fpc(case: str):
    body, registers = programs.CASES[case][:2]
    machine, fpc = run_hlasm_fpc(programs.program(body))

    assert (machine.restricted_to(registers), fpc) == (
        programs.expected(case),
        programs.CASES[case][4],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.TRAPS))
def test_dfp_conversion_trap_delivers_or_suppresses_then_abends_with_the_dxc(
    case: str,
):
    body, fprs = programs.TRAPS[case][:2]
    machine, fpr_images, fpc = run_hlasm_float(programs.program(body))

    assert (machine.run, machine.cc, {r: fpr_images[r] for r in fprs}, fpc) == (
        programs.expected_trap(case)
    )
