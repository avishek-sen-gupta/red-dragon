# pyright: standard
"""Branch and link, branch and save, branch and set mode, and the addressing-mode instructions, in a machine fixed in AMODE 31."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.data_movement import relative_target, storage_address
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    AMODE_31_LINK_BIT,
    OPERATION_EXCEPTION_ABEND,
    RETURN_SENTINEL,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.storage_layout import section_var
from interpreter.instructions import BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Target = Callable[[HlasmEmitter, MachineStatement], Register]
type Effect = Callable[[HlasmEmitter, MachineStatement], None]
type BranchTo = Callable[[HlasmEmitter, Register], None]

NO_REGISTER = 0
FIRST_OPERAND = 0
SECOND_OPERAND = 1
AMODE_64_BIT = 1
MODE_BITS = AMODE_31_LINK_BIT | AMODE_64_BIT
AMODE_31_CC = 1


def _next_address(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    base = emitter.load_var(section_var(statement.section))
    after = emitter.int_(statement.offset + statement.length)
    return emitter.binop(BinopKind.ADD, base, after)


def _link(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    link = emitter.binop(
        BinopKind.BIT_OR,
        _next_address(emitter, statement),
        emitter.int_(AMODE_31_LINK_BIT),
    )
    emitter.store_gr32(reg_operand(statement, FIRST_OPERAND), link)


def _insert_mode_bit(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    r1 = reg_operand(statement, FIRST_OPERAND)
    if r1 == NO_REGISTER:
        return
    marked = emitter.binop(
        BinopKind.BIT_OR, emitter.load_gr32(r1), emitter.int_(AMODE_31_LINK_BIT)
    )
    emitter.store_gr32(r1, marked)


def _returning(emitter: HlasmEmitter, target: Register) -> Register:
    address = emitter.binop(BinopKind.BIT_AND, target, emitter.int_(ADDRESS_MASK_31))
    return emitter.binop(BinopKind.EQ, address, emitter.int_(RETURN_SENTINEL))


def _stays_in_amode_31(emitter: HlasmEmitter, target: Register) -> Register:
    mode = emitter.binop(BinopKind.BIT_AND, target, emitter.int_(MODE_BITS))
    return emitter.binop(BinopKind.EQ, mode, emitter.int_(AMODE_31_LINK_BIT))


def _branch_when(
    emitter: HlasmEmitter, condition: Register, taken: CodeLabel, prefix: str
) -> None:
    fall = emitter.fresh_label(prefix)
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, fall)))
    emitter.emit_inst(Label_(label=fall))


def _set_mode_and_branch(emitter: HlasmEmitter, target: Register) -> None:
    amode_31 = emitter.fresh_label("hl_amode_31")
    _branch_when(emitter, _returning(emitter, target), amode_31, "hl_amode_test")
    _branch_when(
        emitter, _stays_in_amode_31(emitter, target), amode_31, "hl_amode_other"
    )
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)
    emitter.emit_inst(Label_(label=amode_31))
    emit_branch(emitter, target)


def _and_link(target: Target) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        to = target(emitter, statement)
        _link(emitter, statement)
        emit_branch(emitter, to)

    return lower


def _register_branch(effect: Effect, branch: BranchTo) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        r2 = reg_operand(statement, SECOND_OPERAND)
        if r2 == NO_REGISTER:
            effect(emitter, statement)
            return
        target = emitter.load_gr32(r2)
        effect(emitter, statement)
        branch(emitter, target)

    return lower


def lower_leave_amode_31(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)


def lower_sam31(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    return


def lower_tam(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    emitter.set_cc(emitter.int_(AMODE_31_CC))


BRANCH_AND_LINK_LOWERINGS: Mapping[str, StatementLowering] = {
    "BAL": _and_link(storage_address),
    "BALR": _register_branch(_link, emit_branch),
    "BAS": _and_link(storage_address),
    "BASR": _register_branch(_link, emit_branch),
    "BRAS": _and_link(relative_target),
    "BRASL": _and_link(relative_target),
    "BASSM": _register_branch(_link, _set_mode_and_branch),
    "BSM": _register_branch(_insert_mode_bit, _set_mode_and_branch),
    "SAM24": lower_leave_amode_31,
    "SAM31": lower_sam31,
    "SAM64": lower_leave_amode_31,
    "TAM": lower_tam,
}
