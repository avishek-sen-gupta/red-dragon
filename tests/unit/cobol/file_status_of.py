"""Runs the IR that maps a driver outcome to the FILE STATUS it reports."""

from __future__ import annotations

from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.file_state import file_state
from interpreter.cobol.file_verb_ir import FileVerbIr
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register
from tests.unit.cobol.emitted_ir import run_emitted


def _status(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
    driver_outcome, program = registers
    v = FileVerbIr(e, file_state("P", "F"), program)
    outcome = v.outcome()
    v.store_status(outcome, driver_outcome)
    return e.load(outcome.status)


def file_status_of(condition: AccessCondition) -> str:
    return str(run_emitted(_status, (condition.value, "P")))
