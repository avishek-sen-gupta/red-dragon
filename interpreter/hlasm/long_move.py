# pyright: standard
"""MOVE LONG, MOVE LONG EXTENDED and MOVE LONG UNICODE: the source moves left to right, then the pad fills the rest, all in one execution; the addresses advance and the lengths count down."""

from collections.abc import Callable

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import copy_byte, emit_counted_loop
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import (
    effective_address,
    register_address,
)
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    BITS_PER_BYTE,
    BYTE_MASK,
    HALFWORD_BYTES,
    LOW_WORD_MASK,
    ONE_BYTE,
    PARAM_LEFT,
    PARAM_RIGHT,
    WORD_BITS,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.long_operands import LongOperands
from interpreter.hlasm.opcodes.compare import LOGICAL_32
from interpreter.hlasm.opcodes.even_odd import even_odd_pairs
from interpreter.hlasm.operands import reg_operand, storage_operand
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Pad = tuple[Register, int]
type Pairs = tuple[int, int]
type LengthCheck = Callable[[HlasmEmitter, LongOperands], None]

MOVE_LONG_LENGTH = 0xFFFFFF
MOVE_LONG_PAD_SHIFT = 24
PAD_OPERAND = 2
ODD_LENGTH = 1
DESTRUCTIVE_OVERLAP_CC = 3


def _length(emitter: HlasmEmitter, r: int, length_mask: int) -> Register:
    return emitter.binop(
        BinopKind.BIT_AND, emitter.load_gr32(r + 1), emitter.int_(length_mask)
    )


def _operands(emitter: HlasmEmitter, pairs: Pairs, length_mask: int) -> LongOperands:
    target, source = pairs
    return LongOperands(
        register_address(emitter, target),
        _length(emitter, target, length_mask),
        register_address(emitter, source),
        _length(emitter, source, length_mask),
    )


def _pairs(statement: MachineStatement) -> Pairs:
    return reg_operand(statement, FIRST_OPERAND), reg_operand(statement, SECOND_OPERAND)


def _smaller(emitter: HlasmEmitter, left: Register, right: Register) -> Register:
    difference = emitter.binop(BinopKind.SUB, left, right)
    borrow = emitter.binop(BinopKind.RSHIFT, difference, emitter.int_(WORD_BITS))
    shortfall = emitter.binop(BinopKind.BIT_AND, difference, borrow)
    return emitter.binop(BinopKind.ADD, right, shortfall)


def _move_then_pad(
    emitter: HlasmEmitter, operands: LongOperands, moved: Register, pad: Pad
) -> None:
    addresses = (operands.target, operands.source)
    emit_counted_loop(
        emitter,
        (emitter.int_(0), moved),
        ONE_BYTE,
        lambda at: copy_byte(emitter, addresses, at),
    )
    image, width = pad
    emit_counted_loop(
        emitter,
        (moved, operands.target_length),
        width,
        lambda at: emitter.write_bytes(operands.target, at, width, image),
    )


def _advance(emitter: HlasmEmitter, r: int, address: Register, count: Register) -> None:
    after = emitter.binop(BinopKind.ADD, address, count)
    emitter.store_gr32(
        r, emitter.binop(BinopKind.BIT_AND, after, emitter.int_(ADDRESS_MASK_31))
    )


def _count_down(
    emitter: HlasmEmitter, r: int, remaining: Register, length_mask: int
) -> None:
    kept = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(r + 1),
        emitter.int_(LOW_WORD_MASK & ~length_mask),
    )
    emitter.store_gr32(r + 1, emitter.binop(BinopKind.BIT_OR, kept, remaining))


def _update_registers(
    emitter: HlasmEmitter,
    pairs: Pairs,
    operands: LongOperands,
    moved: Register,
    length_mask: int,
) -> None:
    target, source = pairs
    zero = emitter.int_(0)
    unmoved = emitter.binop(BinopKind.SUB, operands.source_length, moved)
    _advance(emitter, target, operands.target, operands.target_length)
    _count_down(emitter, target, zero, length_mask)
    _advance(emitter, source, operands.source, moved)
    _count_down(emitter, source, unmoved, length_mask)


def _complete(
    emitter: HlasmEmitter,
    pairs: Pairs,
    operands: LongOperands,
    pad: Pad,
    length_mask: int,
) -> None:
    lengths = {PARAM_LEFT: operands.target_length, PARAM_RIGHT: operands.source_length}
    cc = inline_ir(emitter, LOGICAL_32, lengths)
    moved = _smaller(emitter, operands.target_length, operands.source_length)
    _move_then_pad(emitter, operands, moved, pad)
    _update_registers(emitter, pairs, operands, moved, length_mask)
    emitter.set_cc(cc)


def _destructive(emitter: HlasmEmitter, operands: LongOperands) -> Register:
    moved = _smaller(emitter, operands.target_length, operands.source_length)
    source_end = emitter.binop(BinopKind.ADD, operands.source, moved)
    return emitter.binop(
        BinopKind.AND,
        emitter.binop(BinopKind.LT, operands.source, operands.target),
        emitter.binop(BinopKind.LT, operands.target, source_end),
    )


def _refuse_destructive_overlap(
    emitter: HlasmEmitter, pairs: Pairs, operands: LongOperands, done: CodeLabel
) -> None:
    overlap, move = emitter.fresh_label("hl_mvcl_overlap"), emitter.fresh_label(
        "hl_mvcl_move"
    )
    destructive = _destructive(emitter, operands)
    emitter.emit_inst(BranchIf(cond_reg=destructive, branch_targets=(overlap, move)))
    emitter.emit_inst(Label_(label=overlap))
    target, source = pairs
    emitter.store_gr32(target, operands.target)
    emitter.store_gr32(source, operands.source)
    emitter.set_cc(emitter.int_(DESTRUCTIVE_OVERLAP_CC))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=move))


def _move_long_pad(emitter: HlasmEmitter, source: int) -> Pad:
    shifted = emitter.binop(
        BinopKind.RSHIFT,
        emitter.load_gr32(source + 1),
        emitter.int_(MOVE_LONG_PAD_SHIFT),
    )
    pad = emitter.binop(BinopKind.BIT_AND, shifted, emitter.int_(BYTE_MASK))
    return emitter.image(pad, ONE_BYTE), ONE_BYTE


def _move_long(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    pairs = _pairs(statement)
    operands = _operands(emitter, pairs, MOVE_LONG_LENGTH)
    done = emitter.fresh_label("hl_mvcl_done")
    _refuse_destructive_overlap(emitter, pairs, operands, done)
    pad = _move_long_pad(emitter, pairs[1])
    _complete(emitter, pairs, operands, pad, MOVE_LONG_LENGTH)
    emitter.emit_inst(Label_(label=done))


def _pad_operand(emitter: HlasmEmitter, statement: MachineStatement, width: int) -> Pad:
    address = effective_address(emitter, storage_operand(statement, PAD_OPERAND))
    pad = emitter.binop(
        BinopKind.BIT_AND,
        address,
        emitter.int_((1 << (BITS_PER_BYTE * width)) - 1),
    )
    return emitter.image(pad, width), width


def _no_length_check(emitter: HlasmEmitter, operands: LongOperands) -> None:
    return


def _even_lengths(emitter: HlasmEmitter, operands: LongOperands) -> None:
    either = emitter.binop(
        BinopKind.BIT_OR, operands.target_length, operands.source_length
    )
    odd = emitter.binop(BinopKind.BIT_AND, either, emitter.int_(ODD_LENGTH))
    emit_specification_check(emitter, emitter.binop(BinopKind.NE, odd, emitter.int_(0)))


def _move_long_extended(width: int, check: LengthCheck) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        pairs = _pairs(statement)
        operands = _operands(emitter, pairs, LOW_WORD_MASK)
        check(emitter, operands)
        pad = _pad_operand(emitter, statement, width)
        _complete(emitter, pairs, operands, pad, LOW_WORD_MASK)

    return even_odd_pairs((FIRST_OPERAND, SECOND_OPERAND), lower)


MOVE_LONG = even_odd_pairs((FIRST_OPERAND, SECOND_OPERAND), _move_long)
MOVE_LONG_EXTENDED = _move_long_extended(ONE_BYTE, _no_length_check)
MOVE_LONG_UNICODE = _move_long_extended(HALFWORD_BYTES, _even_lengths)
