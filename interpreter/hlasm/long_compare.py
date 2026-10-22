# pyright: standard
"""COMPARE LOGICAL LONG, LONG EXTENDED and LONG UNICODE: the operands compare left to right, the shorter extended with the pad, in one execution; each operand advances by the units compared, at most its length."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.hlasm_constants import (
    BYTE_LOOP_AT_VAR,
    HALFWORD_BYTES,
    LOW_WORD_MASK,
    ONE_BYTE,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
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
    smaller,
)
from interpreter.hlasm.long_spans import walk_spans
from interpreter.hlasm.opcodes.even_odd import even_odd_pairs
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.unequal_order import emit_unequal_order
from interpreter.instructions import BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

EQUAL_CC = 0


def _stop_when_unequal(
    emitter: HlasmEmitter, unequal: CodeLabel, images: tuple[Register, Register]
) -> None:
    first, second = images
    differ, same = emitter.fresh_label("hl_clcl_differ"), emitter.fresh_label(
        "hl_clcl_same"
    )
    differs = emitter.binop(BinopKind.NE, first, second)
    emitter.emit_inst(BranchIf(cond_reg=differs, branch_targets=(differ, same)))
    emitter.emit_inst(Label_(label=differ))
    emit_unequal_order(emitter, images, unequal)
    emitter.emit_inst(Label_(label=same))


def _advance_operand(
    emitter: HlasmEmitter,
    r: int,
    operand: tuple[Register, Register],
    compared: Register,
    length_mask: int,
) -> None:
    address, length = operand
    advanced = smaller(emitter, compared, length)
    advance_address(emitter, r, address, advanced)
    count_down(emitter, r, emitter.binop(BinopKind.SUB, length, advanced), length_mask)


def _update_registers(
    emitter: HlasmEmitter, pairs: Pairs, operands: LongOperands, length_mask: int
) -> None:
    first, second = pairs
    compared = emitter.load_var(BYTE_LOOP_AT_VAR)
    _advance_operand(
        emitter, first, (operands.first, operands.first_length), compared, length_mask
    )
    _advance_operand(
        emitter,
        second,
        (operands.second, operands.second_length),
        compared,
        length_mask,
    )


def _compare(
    emitter: HlasmEmitter,
    pairs: Pairs,
    operands: LongOperands,
    pad: Pad,
    length_mask: int,
) -> None:
    unequal = emitter.fresh_label("hl_clcl_unequal")
    walk_spans(
        emitter,
        operands,
        pad,
        lambda at, first, second: _stop_when_unequal(emitter, unequal, (first, second)),
    )
    emitter.set_cc(emitter.int_(EQUAL_CC))
    emitter.emit_inst(Label_(label=unequal))
    _update_registers(emitter, pairs, operands, length_mask)


def _compare_long(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    pairs = operand_pairs(statement)
    operands = long_operands(emitter, pairs, LONG_LENGTH)
    _compare(emitter, pairs, operands, register_pad(emitter, pairs[1]), LONG_LENGTH)


def _compare_long_extended(width: int, check: LengthCheck) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        pairs = operand_pairs(statement)
        operands = long_operands(emitter, pairs, LOW_WORD_MASK)
        check(emitter, operands)
        pad = address_pad(emitter, statement, width)
        _compare(emitter, pairs, operands, pad, LOW_WORD_MASK)

    return even_odd_pairs((FIRST_OPERAND, SECOND_OPERAND), lower)


COMPARE_LONG = even_odd_pairs((FIRST_OPERAND, SECOND_OPERAND), _compare_long)
COMPARE_LONG_EXTENDED = _compare_long_extended(ONE_BYTE, no_length_check)
COMPARE_LONG_UNICODE = _compare_long_extended(HALFWORD_BYTES, even_lengths)
