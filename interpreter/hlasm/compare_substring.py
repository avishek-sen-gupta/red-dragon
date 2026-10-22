# pyright: standard
"""COMPARE UNTIL SUBSTRING EQUAL: scans both operands, the shorter extended with the GR1 pad, for equal runs of the GR0 substring length, in one execution; each operand advances to the start of the last equal run, at most its length."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import register_address
from interpreter.hlasm.hlasm_constants import (
    BYTE_MASK,
    LOW_WORD_MASK,
    ONE_BYTE,
    SUBSTRING_START_VAR,
    WORD_BITS,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_operands import LongOperands
from interpreter.hlasm.long_registers import (
    Pairs,
    advance_address,
    count_down,
    operand_pairs,
    smaller,
)
from interpreter.hlasm.long_spans import walk_spans
from interpreter.hlasm.opcodes.even_odd import even_odd_pairs
from interpreter.hlasm.unequal_order import emit_cc_constant
from interpreter.instructions import Branch, BranchIf, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

SUBSTRING_LENGTH_REGISTER = 0
PAD_REGISTER = 1
FOUND_CC = 0
ENDED_EQUAL_CC = 1
ENDED_UNEQUAL_CC = 2

type Lengths = tuple[Register, Register]


def _low_byte(emitter: HlasmEmitter, r: int) -> Register:
    return emitter.binop(
        BinopKind.BIT_AND, emitter.load_gr32(r), emitter.int_(BYTE_MASK)
    )


def _counted_length(emitter: HlasmEmitter, length: Register) -> Register:
    sign = emitter.binop(BinopKind.RSHIFT, length, emitter.int_(WORD_BITS - 1))
    kept = emitter.binop(BinopKind.SUB, sign, emitter.int_(1))
    return emitter.binop(BinopKind.BIT_AND, length, kept)


def _operands(emitter: HlasmEmitter, pairs: Pairs) -> tuple[LongOperands, Lengths]:
    first, second = pairs
    written = (emitter.load_gr32(first + 1), emitter.load_gr32(second + 1))
    first_length, second_length = (_counted_length(emitter, w) for w in written)
    operands = LongOperands(
        register_address(emitter, first),
        first_length,
        register_address(emitter, second),
        second_length,
        smaller(emitter, first_length, second_length),
    )
    return operands, written


def _restart_after(
    emitter: HlasmEmitter, unequal: CodeLabel, after: Register, then: CodeLabel
) -> None:
    emitter.emit_inst(Label_(label=unequal))
    emitter.emit_inst(StoreVar(name=SUBSTRING_START_VAR, value_reg=after))
    emitter.emit_inst(Branch(label=then))


def _extend_run(
    emitter: HlasmEmitter,
    labels: tuple[CodeLabel, CodeLabel, CodeLabel],
    after: Register,
    substring: Register,
) -> None:
    equal, next_byte, found = labels
    emitter.emit_inst(Label_(label=equal))
    run = emitter.binop(BinopKind.SUB, after, emitter.load_var(SUBSTRING_START_VAR))
    short = emitter.binop(BinopKind.LT, run, substring)
    emitter.emit_inst(BranchIf(cond_reg=short, branch_targets=(next_byte, found)))


def _track_run(
    emitter: HlasmEmitter,
    found: CodeLabel,
    constants: tuple[Register, Register],
    unit: tuple[Register, Register, Register],
) -> None:
    substring, one = constants
    at, first, second = unit
    after = emitter.binop(BinopKind.ADD, at, one)
    unequal, equal, next_byte = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_cuse_unequal", "hl_cuse_equal", "hl_cuse_next")
    )
    differs = emitter.binop(BinopKind.NE, first, second)
    emitter.emit_inst(BranchIf(cond_reg=differs, branch_targets=(unequal, equal)))
    _restart_after(emitter, unequal, after, next_byte)
    _extend_run(emitter, (equal, next_byte, found), after, substring)
    emitter.emit_inst(Label_(label=next_byte))


def _ended_cc(emitter: HlasmEmitter, operands: LongOperands, update: CodeLabel) -> None:
    longer = emitter.binop(
        BinopKind.SUB,
        emitter.binop(BinopKind.ADD, operands.first_length, operands.second_length),
        operands.shorter,
    )
    start = emitter.load_var(SUBSTRING_START_VAR)
    ended_equal, ended_unequal = emitter.fresh_label(
        "hl_cuse_ended_equal"
    ), emitter.fresh_label("hl_cuse_ended_unequal")
    last_equal = emitter.binop(BinopKind.LT, start, longer)
    emitter.emit_inst(
        BranchIf(cond_reg=last_equal, branch_targets=(ended_equal, ended_unequal))
    )
    emit_cc_constant(emitter, ENDED_EQUAL_CC, ended_equal, update)
    emit_cc_constant(emitter, ENDED_UNEQUAL_CC, ended_unequal, update)


def _advance_operand(
    emitter: HlasmEmitter,
    r: int,
    operand: tuple[Register, Register, Register],
    start: Register,
) -> None:
    address, length, written = operand
    advanced = smaller(emitter, start, length)
    advance_address(emitter, r, address, advanced)
    count_down(
        emitter, r, emitter.binop(BinopKind.SUB, written, advanced), LOW_WORD_MASK
    )


def _update_registers(
    emitter: HlasmEmitter, pairs: Pairs, operands: LongOperands, written: Lengths
) -> None:
    start = emitter.load_var(SUBSTRING_START_VAR)
    _advance_operand(
        emitter,
        pairs[0],
        (operands.first, operands.first_length, written[0]),
        start,
    )
    _advance_operand(
        emitter,
        pairs[1],
        (operands.second, operands.second_length, written[1]),
        start,
    )


def _search(
    emitter: HlasmEmitter,
    operands: LongOperands,
    substring: Register,
    labels: tuple[CodeLabel, CodeLabel],
) -> None:
    found, update = labels
    search = emitter.fresh_label("hl_cuse_search")
    empty = emitter.binop(BinopKind.EQ, substring, emitter.int_(0))
    emitter.emit_inst(BranchIf(cond_reg=empty, branch_targets=(found, search)))
    emitter.emit_inst(Label_(label=search))
    pad = emitter.image(_low_byte(emitter, PAD_REGISTER), ONE_BYTE)
    constants = (substring, emitter.int_(ONE_BYTE))
    walk_spans(
        emitter,
        operands,
        (pad, ONE_BYTE),
        lambda at, first, second: _track_run(
            emitter, found, constants, (at, first, second)
        ),
    )
    _ended_cc(emitter, operands, update)


def _compare_until_substring_equal(
    emitter: HlasmEmitter, statement: MachineStatement
) -> None:
    substring = _low_byte(emitter, SUBSTRING_LENGTH_REGISTER)
    pairs = operand_pairs(statement)
    operands, written = _operands(emitter, pairs)
    emitter.emit_inst(StoreVar(name=SUBSTRING_START_VAR, value_reg=emitter.int_(0)))
    found, update = emitter.fresh_label("hl_cuse_found"), emitter.fresh_label(
        "hl_cuse_update"
    )
    _search(emitter, operands, substring, (found, update))
    emit_cc_constant(emitter, FOUND_CC, found, update)
    emitter.emit_inst(Label_(label=update))
    _update_registers(emitter, pairs, operands, written)


COMPARE_UNTIL_SUBSTRING_EQUAL = even_odd_pairs(
    (FIRST_OPERAND, SECOND_OPERAND), _compare_until_substring_equal
)
