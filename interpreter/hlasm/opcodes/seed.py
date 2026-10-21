# pyright: standard
"""Seed opcodes: LA, LR, SR, the register branches BCR, BASR, BALR and BRAS."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.branch_dispatch import emit_branch
from interpreter.hlasm.effective_address import effective_address
from interpreter.hlasm.fixed_width_ir import build_sub_signed_cc_ir
from interpreter.hlasm.hlasm_constants import (
    AMODE_31_LINK_BIT,
    CC_VAR,
    PARAM_LEFT,
    PARAM_RIGHT,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.storage_layout import section_var
from interpreter.instructions import BranchIf, Label_, LoadIndex
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

_SUB_32 = build_sub_signed_cc_ir("hlasm.sub32", 32)
_CC_MASK_TOP = 8
_ALWAYS = 15


def _reg(statement: MachineStatement, at: int) -> int:
    operand = statement.operands[at]
    assert isinstance(operand, RegOperand)
    return operand.value


def _mask(statement: MachineStatement) -> int:
    operand = statement.operands[0]
    assert isinstance(operand, MaskOperand)
    return operand.value


def _storage(statement: MachineStatement) -> StorageOperand:
    operand = statement.operands[1]
    assert isinstance(operand, StorageOperand)
    return operand


def _element(emitter: HlasmEmitter, pair: Register, at: int) -> Register:
    reg = emitter.fresh_reg()
    emitter.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=pair, index_reg=emitter.int_(at))
    )
    return reg


def lower_la(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    emitter.store_gr32(
        _reg(statement, 0), effective_address(emitter, _storage(statement))
    )


def lower_lr(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    emitter.store_gr32(_reg(statement, 0), emitter.load_gr32(_reg(statement, 1)))


def lower_sr(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    r1 = _reg(statement, 0)
    pair = inline_ir(
        emitter,
        _SUB_32,
        {
            PARAM_LEFT: emitter.load_gr32(r1),
            PARAM_RIGHT: emitter.load_gr32(_reg(statement, 1)),
        },
    )
    emitter.store_gr32(r1, _element(emitter, pair, 0))
    emitter.set_cc(_element(emitter, pair, 1))


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
    emitter.store_gr32(_reg(statement, 0), link)


def _relative_target(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    operand = statement.operands[1]
    assert isinstance(operand, RelocImmOperand)
    base = emitter.load_var(section_var(operand.section))
    return emitter.binop(BinopKind.ADD, base, emitter.int_(operand.offset))


def lower_branch_and_link(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    r2 = _reg(statement, 1)
    target = emitter.load_gr32(r2)
    _link(emitter, statement)
    if r2 == 0:
        return
    emit_branch(emitter, target)


def lower_bras(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    target = _relative_target(emitter, statement)
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
    mask, r2 = _mask(statement), _reg(statement, 1)
    if mask == 0 or r2 == 0:
        return
    if mask == _ALWAYS:
        emit_branch(emitter, emitter.load_gr32(r2))
        return
    _conditional_branch(emitter, mask, r2)


SEED_LOWERINGS: Mapping[str, StatementLowering] = {
    "LA": lower_la,
    "LR": lower_lr,
    "SR": lower_sr,
    "BCR": lower_bcr,
    "BASR": lower_branch_and_link,
    "BALR": lower_branch_and_link,
    "BRAS": lower_bras,
}
