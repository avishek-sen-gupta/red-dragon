# pyright: standard
"""Seed opcodes: LR, the register branches BCR, BASR, BALR and BRAS."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.effective_address import relative_address
from interpreter.hlasm.hlasm_constants import AMODE_31_LINK_BIT, CC_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import (
    mask_operand,
    reg_operand,
    reloc_operand,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.storage_layout import section_var
from interpreter.instructions import BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

_CC_MASK_TOP = 8
_ALWAYS = 15


def lower_lr(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    emitter.store_gr32(
        reg_operand(statement, 0), emitter.load_gr32(reg_operand(statement, 1))
    )


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
    emitter.store_gr32(reg_operand(statement, 0), link)


def lower_branch_and_link(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    r2 = reg_operand(statement, 1)
    target = emitter.load_gr32(r2)
    _link(emitter, statement)
    if r2 == 0:
        return
    emit_branch(emitter, target)


def lower_bras(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    target = relative_address(emitter, reloc_operand(statement, 1))
    _link(emitter, statement)
    emit_branch(emitter, target)


def _conditional_branch(emitter: HlasmEmitter, mask: int, r2: int) -> None:
    shifted = emitter.binop(
        BinopKind.RSHIFT, emitter.int_(_CC_MASK_TOP), emitter.load_var(CC_VAR)
    )
    selected = emitter.binop(BinopKind.BIT_AND, shifted, emitter.int_(mask))
    taken = emitter.binop(BinopKind.NE, selected, emitter.int_(0))
    taken_label = emitter.fresh_label("hl_bcr_taken")
    fall_label = emitter.fresh_label("hl_bcr_fall")
    emitter.emit_inst(
        BranchIf(cond_reg=taken, branch_targets=(taken_label, fall_label))
    )
    emitter.emit_inst(Label_(label=taken_label))
    emit_branch(emitter, emitter.load_gr32(r2))
    emitter.emit_inst(Label_(label=fall_label))


def lower_bcr(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    mask, r2 = mask_operand(statement, 0), reg_operand(statement, 1)
    if mask == 0 or r2 == 0:
        return
    if mask == _ALWAYS:
        emit_branch(emitter, emitter.load_gr32(r2))
        return
    _conditional_branch(emitter, mask, r2)


SEED_LOWERINGS: Mapping[str, StatementLowering] = {
    "LR": lower_lr,
    "BCR": lower_bcr,
    "BASR": lower_branch_and_link,
    "BALR": lower_branch_and_link,
    "BRAS": lower_bras,
}
