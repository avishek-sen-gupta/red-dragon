# pyright: standard
"""EX and EXRL run on the VM: the target modified by bits 56-63 of R1 runs in place of the execute instruction, its link after it, its CC kept; execute and specification exceptions abend."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import execute_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_execute_runs_the_modified_target(case: str):
    code, run, cc, registers = programs.CASES[case]
    machine = run_hlasm_machine(programs.program(code))

    assert programs.view(machine, registers) == HlasmMachine(run, cc, registers)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.xfail(
    reason="an indexed EX target is not resolved statically; it abends S0C1 — red-dragon-6uyp.77",
    strict=True,
)
def test_execute_an_indexed_target():
    code, run, cc, registers = programs.INDEXED_TARGET
    machine = run_hlasm_machine(programs.program(code))

    assert programs.view(machine, registers) == HlasmMachine(run, cc, registers)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.xfail(
    reason="R1 bits ORed into opcode bits are not modelled; they abend S0C1 — red-dragon-6uyp.78",
    strict=True,
)
def test_execute_modifies_an_opcode():
    code, run, cc, registers = programs.MODIFIED_OPCODE
    machine = run_hlasm_machine(programs.program(code))

    assert programs.view(machine, registers) == HlasmMachine(run, cc, registers)
