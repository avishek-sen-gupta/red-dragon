# pyright: standard
"""MOVE LONG, MOVE LONG EXTENDED and MOVE LONG UNICODE: the source moves left to right, then the pad fills the rest, all in one execution; the addresses advance and the lengths count down."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import copy_byte, emit_counted_loop
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.hlasm_constants import (
    HALFWORD_BYTES,
    LOW_WORD_MASK,
    ONE_BYTE,
    PARAM_LEFT,
    PARAM_RIGHT,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.long_operands import LongOperands
from interpreter.hlasm.long_registers import (
    LONG_LENGTH,
    LengthCheck,
    Pad,
    Pairs,
    address_pad,
    advance_address,
    count_down,
    even_lengths,
    long_operands,
    no_length_check,
    operand_pairs,
    register_pad,
)
from interpreter.hlasm.opcodes.compare import LOGICAL_32
from interpreter.hlasm.opcodes.even_odd import even_odd_pairs
from interpreter.hlasm.operand_overlap import starts_inside_source
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind

DESTRUCTIVE_OVERLAP_CC = 3


def _move_then_pad(emitter: HlasmEmitter, operands: LongOperands, pad: Pad) -> None:
    moved = operands.shorter
    addresses = (operands.first, operands.second)
    emit_counted_loop(
        emitter,
        (emitter.int_(0), moved),
        ONE_BYTE,
        lambda at: copy_byte(emitter, addresses, at),
    )
    value, width = pad
    image = emitter.image(value, width)
    emit_counted_loop(
        emitter,
        (moved, operands.first_length),
        width,
        lambda at: emitter.write_bytes(operands.first, at, width, image),
    )


def _update_registers(
    emitter: HlasmEmitter,
    pairs: Pairs,
    operands: LongOperands,
    length_mask: int,
) -> None:
    target, source = pairs
    moved = operands.shorter
    zero = emitter.int_(0)
    unmoved = emitter.binop(BinopKind.SUB, operands.second_length, moved)
    advance_address(emitter, target, operands.first, operands.first_length)
    count_down(emitter, target, zero, length_mask)
    advance_address(emitter, source, operands.second, moved)
    count_down(emitter, source, unmoved, length_mask)


def _complete(
    emitter: HlasmEmitter,
    pairs: Pairs,
    operands: LongOperands,
    pad: Pad,
    length_mask: int,
) -> None:
    lengths = {PARAM_LEFT: operands.first_length, PARAM_RIGHT: operands.second_length}
    cc = inline_ir(emitter, LOGICAL_32, lengths)
    _move_then_pad(emitter, operands, pad)
    _update_registers(emitter, pairs, operands, length_mask)
    emitter.set_cc(cc)


def _refuse_destructive_overlap(
    emitter: HlasmEmitter, pairs: Pairs, operands: LongOperands, done: CodeLabel
) -> None:
    overlap, move = emitter.fresh_label("hl_mvcl_overlap"), emitter.fresh_label(
        "hl_mvcl_move"
    )
    destructive = starts_inside_source(
        emitter, (operands.first, operands.second), operands.shorter
    )
    emitter.emit_inst(BranchIf(cond_reg=destructive, branch_targets=(overlap, move)))
    emitter.emit_inst(Label_(label=overlap))
    target, source = pairs
    emitter.store_gr32(target, operands.first)
    emitter.store_gr32(source, operands.second)
    emitter.set_cc(emitter.int_(DESTRUCTIVE_OVERLAP_CC))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=move))


def _move_long(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    pairs = operand_pairs(statement)
    operands = long_operands(emitter, pairs, LONG_LENGTH)
    done = emitter.fresh_label("hl_mvcl_done")
    _refuse_destructive_overlap(emitter, pairs, operands, done)
    pad = register_pad(emitter, pairs[1])
    _complete(emitter, pairs, operands, pad, LONG_LENGTH)
    emitter.emit_inst(Label_(label=done))


def _move_long_extended(width: int, check: LengthCheck) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        pairs = operand_pairs(statement)
        operands = long_operands(emitter, pairs, LOW_WORD_MASK)
        check(emitter, operands)
        pad = address_pad(emitter, statement, width)
        _complete(emitter, pairs, operands, pad, LOW_WORD_MASK)

    return even_odd_pairs((FIRST_OPERAND, SECOND_OPERAND), lower)


MOVE_LONG = even_odd_pairs((FIRST_OPERAND, SECOND_OPERAND), _move_long)
MOVE_LONG_EXTENDED = _move_long_extended(ONE_BYTE, no_length_check)
MOVE_LONG_UNICODE = _move_long_extended(HALFWORD_BYTES, even_lengths)
