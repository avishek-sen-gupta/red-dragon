# pyright: standard
"""Load and store on condition, select, and the population and bit counts: the CC picks a move or an operand, the counts are built in IR."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bit_counts import (
    any_one,
    leading_zeros,
    leading_zeros_of_smear,
    leftmost_one,
    population,
    population_by_byte,
    smeared_right,
    trailing_zeros,
)
from interpreter.hlasm.conditional import emit_when, pick
from interpreter.hlasm.data_movement import (
    REGISTER_OPERAND,
    Sink,
    Source,
    Transform,
    from_gr32,
    from_gr64,
    from_gr_high32,
    move,
    to_gr32,
    to_gr64,
    to_gr_high32,
    to_storage,
)
from interpreter.hlasm.hlasm_constants import (
    CC_VAR,
    DOUBLEWORD_BYTES,
    PARAM_VALUE,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.mask_bit_loop import deposited_bits, extracted_bits
from interpreter.hlasm.opcodes.branch_on_condition import mask_selects
from interpreter.hlasm.opcodes.even_odd import even_odd
from interpreter.hlasm.opcodes.operand_sources import (
    DOUBLEWORD_STORAGE,
    HALFWORD_IMMEDIATE,
    WORD_STORAGE,
)
from interpreter.hlasm.opcodes.shift_rotate import NONZERO_64
from interpreter.hlasm.operands import mask_operand, optional_mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type MaskedBits = Callable[[HlasmEmitter, Register, Register], Register]

CONDITION_MASK_OPERAND = 2
SELECT_MASK_OPERAND = 3
POPCNT_MASK_OPERAND = 2
PER_BYTE = 0
TOTAL_COUNT = 0b1000
SECOND_REGISTER = 1
THIRD_REGISTER = 2
FOUND_CC_SHIFT = 1


def _selects(emitter: HlasmEmitter, statement: MachineStatement, at: int) -> Register:
    return mask_selects(emitter, emitter.load_var(CC_VAR), mask_operand(statement, at))


def _on_condition(lowering: StatementLowering) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        selected = _selects(emitter, statement, CONDITION_MASK_OPERAND)
        emit_when(emitter, selected, lambda: lowering(emitter, statement))

    return lower


def _select(source_of: Callable[[int], Source], sink: Sink) -> StatementLowering:
    second, third = source_of(SECOND_REGISTER), source_of(THIRD_REGISTER)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        chosen, otherwise = second(emitter, statement), third(emitter, statement)
        selected = _selects(emitter, statement, SELECT_MASK_OPERAND)
        sink(emitter, statement, pick(emitter, selected, chosen, otherwise))

    return lower


def lower_find_leftmost_one(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    value = emitter.load_gr64(reg_operand(statement, SECOND_REGISTER))
    smeared = smeared_right(emitter, value)
    r1 = reg_operand(statement, REGISTER_OPERAND)
    emitter.store_gr64(r1, leading_zeros_of_smear(emitter, smeared))
    cleared = emitter.binop(BinopKind.BIT_XOR, value, leftmost_one(emitter, smeared))
    emitter.store_gr64(r1 + 1, cleared)
    found = any_one(emitter, smeared)
    emitter.set_cc(emitter.binop(BinopKind.LSHIFT, found, emitter.int_(FOUND_CC_SHIFT)))


_COUNTS: Mapping[bool, Transform] = {
    False: population_by_byte,
    True: population,
}


def lower_population_count(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    total = bool(
        optional_mask_operand(statement, POPCNT_MASK_OPERAND, PER_BYTE) & TOTAL_COUNT
    )
    value = emitter.load_gr64(reg_operand(statement, SECOND_REGISTER))
    result = _COUNTS[total](emitter, value)
    to_gr64(emitter, statement, result)
    emitter.set_cc(inline_ir(emitter, NONZERO_64, {PARAM_VALUE: result}))


def _under_mask(bits: MaskedBits) -> StatementLowering:
    value_of, mask_of = from_gr64(SECOND_REGISTER), from_gr64(THIRD_REGISTER)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        value, mask = value_of(emitter, statement), mask_of(emitter, statement)
        to_gr64(emitter, statement, bits(emitter, value, mask))

    return lower


LOAD_ON_CONDITION: Mapping[str, StatementLowering] = {
    "LOCR": _on_condition(move(from_gr32(1), (), to_gr32)),
    "LOCGR": _on_condition(move(from_gr64(1), (), to_gr64)),
    "LOCFHR": _on_condition(move(from_gr_high32(1), (), to_gr_high32)),
    "LOC": _on_condition(move(WORD_STORAGE, (), to_gr32)),
    "LOCG": _on_condition(move(DOUBLEWORD_STORAGE, (), to_gr64)),
    "LOCFH": _on_condition(move(WORD_STORAGE, (), to_gr_high32)),
    "LOCHI": _on_condition(move(HALFWORD_IMMEDIATE, (), to_gr32)),
    "LOCGHI": _on_condition(move(HALFWORD_IMMEDIATE, (), to_gr64)),
    "LOCHHI": _on_condition(move(HALFWORD_IMMEDIATE, (), to_gr_high32)),
}

STORE_ON_CONDITION: Mapping[str, StatementLowering] = {
    "STOC": _on_condition(move(from_gr32(0), (), to_storage(WORD_BYTES))),
    "STOCG": _on_condition(move(from_gr64(0), (), to_storage(DOUBLEWORD_BYTES))),
    "STOCFH": _on_condition(move(from_gr_high32(0), (), to_storage(WORD_BYTES))),
}

SELECT: Mapping[str, StatementLowering] = {
    "SELR": _select(from_gr32, to_gr32),
    "SELGR": _select(from_gr64, to_gr64),
    "SELFHR": _select(from_gr_high32, to_gr_high32),
}

BIT_COUNTS: Mapping[str, StatementLowering] = {
    "FLOGR": even_odd(lower_find_leftmost_one),
    "POPCNT": lower_population_count,
    "CLZG": move(from_gr64(SECOND_REGISTER), (leading_zeros,), to_gr64),
    "CTZG": move(from_gr64(SECOND_REGISTER), (trailing_zeros,), to_gr64),
    "BEXTG": _under_mask(extracted_bits),
    "BDEPG": _under_mask(deposited_bits),
}

CONDITIONAL_SELECT_COUNT_LOWERINGS: Mapping[str, StatementLowering] = {
    **LOAD_ON_CONDITION,
    **STORE_ON_CONDITION,
    **SELECT,
    **BIT_COUNTS,
}
