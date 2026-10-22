# pyright: standard
"""MOVE STRING: copies through the ending character in GR0 bits 56-63 in one execution, leaves R1 at that character in the destination and sets CC 1."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import advance, copied_byte
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import register_address
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    BYTE_LOOP_AT_VAR,
    BYTE_MASK,
    ONE_BYTE,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.instructions import BranchIf, Label_, LoadIndex, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

ENDING_CHARACTER_REGISTER = 0
RESERVED_BITS = 0xFFFFFF00
ENDING_CHARACTER_MOVED_CC = 1


def _ending_character(emitter: HlasmEmitter) -> Register:
    gr0 = emitter.load_gr32(ENDING_CHARACTER_REGISTER)
    reserved = emitter.binop(BinopKind.BIT_AND, gr0, emitter.int_(RESERVED_BITS))
    emit_specification_check(
        emitter, emitter.binop(BinopKind.NE, reserved, emitter.int_(0))
    )
    return emitter.binop(BinopKind.BIT_AND, gr0, emitter.int_(BYTE_MASK))


def _stop_at_ending(
    emitter: HlasmEmitter,
    copied: tuple[Register, Register],
    ending: Register,
    targets: tuple[CodeLabel, CodeLabel],
) -> None:
    image, first = copied
    byte = emitter.fresh_reg()
    emitter.emit_inst(LoadIndex(result_reg=byte, arr_reg=image, index_reg=first))
    ended = emitter.binop(BinopKind.EQ, byte, ending)
    emitter.emit_inst(BranchIf(cond_reg=ended, branch_targets=targets))


def _copy_through(
    emitter: HlasmEmitter, addresses: tuple[Register, Register], ending: Register
) -> Register:
    first, step = emitter.int_(0), emitter.int_(ONE_BYTE)
    emitter.emit_inst(StoreVar(name=BYTE_LOOP_AT_VAR, value_reg=first))
    loop, more, done = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_mvst_loop", "hl_mvst_more", "hl_mvst_done")
    )
    emitter.emit_inst(Label_(label=loop))
    at = emitter.load_var(BYTE_LOOP_AT_VAR)
    copied = (copied_byte(emitter, addresses, at), first)
    _stop_at_ending(emitter, copied, ending, (done, more))
    emitter.emit_inst(Label_(label=more))
    advance(emitter, at, step, loop)
    emitter.emit_inst(Label_(label=done))
    return at


def move_string(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    target_register = reg_operand(statement, FIRST_OPERAND)
    ending = _ending_character(emitter)
    target = register_address(emitter, target_register)
    source = register_address(emitter, reg_operand(statement, SECOND_OPERAND))
    at = _copy_through(emitter, (target, source), ending)
    ended_at = emitter.binop(BinopKind.ADD, target, at)
    emitter.store_gr32(
        target_register,
        emitter.binop(BinopKind.BIT_AND, ended_at, emitter.int_(ADDRESS_MASK_31)),
    )
    emitter.set_cc(emitter.int_(ENDING_CHARACTER_MOVED_CC))
