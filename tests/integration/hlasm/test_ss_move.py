# pyright: standard
"""The bridge gives SS lengths as written; storage moves run on the VM leave the Principles of Operation storage, registers and CC, overlapping operands included, and abend S0C6 on a specification exception."""

from pathlib import Path

import pytest

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from interpreter.frontends import get_hlasm_parser
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import ss_move_programs as programs
from tests.integration.hlasm.hlasm_helpers import BARE_ASSEMBLY, run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_move_leaves_the_storage_registers_and_cc(case: str):
    body, results, cc = programs.CASES[case]
    machine = run_hlasm_machine(programs.move_program(body))

    assert machine.restricted_to(results) == HlasmMachine(ABENDED, cc, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.SPECIFICATION_EXCEPTIONS))
def test_specification_exception_abends_s0c6_and_leaves_the_registers(case: str):
    body, results, cc = programs.SPECIFICATION_EXCEPTIONS[case]
    machine = run_hlasm_machine(programs.move_program(body))

    assert machine.restricted_to(results) == HlasmMachine(SPECIFICATION, cc, results)


MVO_LENGTHS = (
    "T        CSECT\n"
    "         USING *,12\n"
    "         MVO   A(3),B(2)\n"
    "         MVO   A,B\n"
    "         MVO   A(1),B(16)\n"
    "A        DS    CL4\n"
    "B        DS    CL5\n"
    "         END\n"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_gives_mvo_lengths_as_written(tmp_path: Path):
    parser = get_hlasm_parser()
    program = parser.read(
        parser.parse_to_file(
            MVO_LENGTHS.encode(), "mvo.asm", tmp_path / "mvo.json", BARE_ASSEMBLY
        )
    )

    assert [
        tuple(
            operand.length
            for operand in statement.operands
            if isinstance(operand, StorageLengthOperand)
        )
        for statement in program.statements
        if isinstance(statement, MachineStatement)
    ] == [(3, 2), (4, 5), (1, 16)]
