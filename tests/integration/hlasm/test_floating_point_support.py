# pyright: standard
"""Floating-point-support instructions run on the VM move FPR bits, keep the low word under short operands, change only the sign bit, load the FPC after its checks and trap simulated IEEE exceptions with the DXC in the FPC; no form changes the CC."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import floating_point_support_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_fpc, run_hlasm_machine


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_floating_point_support_instruction_leaves_the_registers_and_cc(case: str):
    body, registers = programs.CASES[case][:2]
    machine = run_hlasm_machine(storage.based_program(body, storage.ABEND))

    assert machine.restricted_to(registers) == programs.expected(case)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CHECKED))
def test_fpc_check_leaves_it_unchanged_and_a_trap_leaves_the_dxc(case: str):
    checked, fpc = programs.CHECKED[case]
    body, registers = checked[:2]
    machine, left = run_hlasm_fpc(storage.based_program(body, storage.ABEND))

    assert (machine.restricted_to(registers), left) == (programs.expected(case), fpc)
