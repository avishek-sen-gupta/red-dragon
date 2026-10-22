# pyright: standard
"""EX and EXRL: the target statement, found at assembly, runs in place of the execute instruction; a byte-1 data field is computed at run time, register and mask fields select one inline copy per value R1 can make."""

import logging
from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.byte_one_layout import ByteOneLayout
from interpreter.hlasm.byte_one_layouts import byte_one_layout
from interpreter.hlasm.executed_field import ExecutedField
from interpreter.hlasm.field_lowering import FieldLowering
from interpreter.hlasm.hlasm_constants import (
    BYTE_MASK,
    EXECUTE_EXCEPTION_ABEND,
    OPERATION_EXCEPTION_ABEND,
    SPECIFICATION_EXCEPTION_ABEND,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.machine_statements import MachineStatements
from interpreter.hlasm.opcodes import DATA_FIELD_LOWERINGS, OPCODE_LOWERINGS
from interpreter.hlasm.operands import (
    reg_operand,
    statement_place,
    storage_operand,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.value_tree import emit_value_switch
from interpreter.instructions import BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

logger = logging.getLogger(__name__)

EXECUTE_EXCEPTION_TARGETS = frozenset(
    {"EX", "EXRL", "TBEGIN", "TBEGINC", "TEND", "TABORT"}
)
R1_OPERAND = 0
TARGET_OPERAND = 1
NO_REGISTER = 0
HALFWORD_ALIGNMENT = 2
UNWRITTEN = "target not written as a relocatable address"

type ExecuteLowering = Callable[
    [HlasmEmitter, MachineStatement, MachineStatements, StatementLowering], None
]


def _unresolved(emitter: HlasmEmitter, statement: MachineStatement, why: str) -> None:
    logger.warning(
        "%s: %s; it abends %s",
        statement_place(statement),
        why,
        OPERATION_EXCEPTION_ABEND,
    )
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)


def _guard_opcode(emitter: HlasmEmitter, ored: Register, opcode_bits: int) -> None:
    if opcode_bits == 0:
        return
    touched = emitter.binop(BinopKind.BIT_AND, ored, emitter.int_(opcode_bits))
    modified = emitter.binop(BinopKind.NE, touched, emitter.int_(0))
    abend, kept = emitter.fresh_label("hl_ex_opcode"), emitter.fresh_label("hl_ex_kept")
    emitter.emit_inst(BranchIf(cond_reg=modified, branch_targets=(abend, kept)))
    emitter.emit_inst(Label_(label=abend))
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)
    emitter.emit_inst(Label_(label=kept))


def _modified_byte(
    emitter: HlasmEmitter, r1: int, target: MachineStatement, layout: ByteOneLayout
) -> Register:
    ored = emitter.binop(
        BinopKind.BIT_AND, emitter.load_gr32(r1), emitter.int_(BYTE_MASK)
    )
    _guard_opcode(emitter, ored, layout.opcode_bits)
    combined = emitter.binop(
        BinopKind.BIT_OR, ored, emitter.int_(layout.byte_of(target))
    )
    return emitter.binop(BinopKind.BIT_AND, combined, emitter.int_(layout.field_bits))


def _expand(
    emitter: HlasmEmitter,
    r1: int,
    target: MachineStatement,
    lower_machine: StatementLowering,
) -> None:
    layout = byte_one_layout(target)
    byte = _modified_byte(emitter, r1, target, layout)
    emit_value_switch(
        emitter,
        byte,
        layout.reachable(target),
        lambda value: lower_machine(emitter, layout.variant(target, value)),
    )


def _with_runtime_field(
    emitter: HlasmEmitter, r1: int, target: MachineStatement, lowering: FieldLowering
) -> None:
    byte = _modified_byte(emitter, r1, target, lowering.layout)
    lowering.lower(emitter, target, ExecutedField(byte))


def _modified(
    emitter: HlasmEmitter,
    r1: int,
    target: MachineStatement,
    lower_machine: StatementLowering,
) -> None:
    if r1 == NO_REGISTER or target.base_mnemonic not in OPCODE_LOWERINGS:
        lower_machine(emitter, target)
        return
    if target.base_mnemonic in DATA_FIELD_LOWERINGS:
        _with_runtime_field(
            emitter, r1, target, DATA_FIELD_LOWERINGS[target.base_mnemonic]
        )
        return
    _expand(emitter, r1, target, lower_machine)


def _execute(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    target: MachineStatement,
    lower_machine: StatementLowering,
) -> None:
    if target.base_mnemonic in EXECUTE_EXCEPTION_TARGETS:
        emit_abend(emitter, EXECUTE_EXCEPTION_ABEND)
        return
    placed = target.model_copy(
        update={
            "section": statement.section,
            "offset": statement.offset,
            "length": statement.length,
        }
    )
    _modified(emitter, reg_operand(statement, R1_OPERAND), placed, lower_machine)


def _execute_at(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    at: RelocAddress,
    statements: MachineStatements,
    lower_machine: StatementLowering,
) -> None:
    if at.offset % HALFWORD_ALIGNMENT:
        emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
        return
    match statements.at(at.section, at.offset):
        case (target,):
            _execute(emitter, statement, target, lower_machine)
        case _:
            why = f"no machine statement at {at.section}+{at.offset}"
            _unresolved(emitter, statement, why)


def _unwritten(operand: StorageOperand) -> str:
    if operand.index:
        return f"target indexed by R{operand.index}"
    return UNWRITTEN


def _lower_ex(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    statements: MachineStatements,
    lower_machine: StatementLowering,
) -> None:
    operand = storage_operand(statement, TARGET_OPERAND)
    match operand:
        case StorageOperand(index=0, written=RelocAddress() as at):
            _execute_at(emitter, statement, at, statements, lower_machine)
        case _:
            _unresolved(emitter, statement, _unwritten(operand))


def _lower_exrl(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    statements: MachineStatements,
    lower_machine: StatementLowering,
) -> None:
    match statement.operands[TARGET_OPERAND]:
        case RelocImmOperand(section=section, offset=offset):
            at = RelocAddress(kind="RELOC", section=section, offset=offset)
            _execute_at(emitter, statement, at, statements, lower_machine)
        case _:
            _unresolved(emitter, statement, UNWRITTEN)


EXECUTE_LOWERINGS: Mapping[str, ExecuteLowering] = {
    "EX": _lower_ex,
    "EXRL": _lower_exrl,
}
EXECUTE_MNEMONICS = frozenset(EXECUTE_LOWERINGS)


def lower_execute(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    statements: MachineStatements,
    lower_machine: StatementLowering,
) -> None:
    EXECUTE_LOWERINGS[statement.base_mnemonic](
        emitter, statement, statements, lower_machine
    )
