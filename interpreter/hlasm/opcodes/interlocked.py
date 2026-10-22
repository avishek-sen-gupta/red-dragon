# pyright: standard
"""Interlocked-update opcodes on one CPU (ruling R33): compare and swap, compare and load, compare and swap and store, load and add or connect, load pair, quadword pairs, test and set, and PLO."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.alignment_check import emit_alignment_check
from interpreter.hlasm.boolean_connective import AND, OR, XOR, BooleanConnective
from interpreter.hlasm.compare_chain import (
    EQUAL_CC,
    emit_cc,
    emit_compare_or_refresh,
)
from interpreter.hlasm.compare_swap_store import lower_compare_and_swap_and_store
from interpreter.hlasm.comparison import Comparison
from interpreter.hlasm.data_movement import (
    REGISTER_OPERAND,
    aligned_storage_address_at,
    from_aligned_storage,
    from_doubleword_pair,
    move,
    storage_address_at,
    to_aligned_storage,
    to_doubleword_pair,
)
from interpreter.hlasm.fixed_point_overflow import emit_fixed_point_overflow_check
from interpreter.hlasm.fixed_width_ir import build_boolean_cc_ir
from interpreter.hlasm.hlasm_constants import (
    BYTE_MASK,
    DOUBLEWORD_BITS,
    DOUBLEWORD_BYTES,
    ONE_BYTE,
    PARAM_LEFT,
    PARAM_RIGHT,
    WORD_BITS,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.even_odd import even_odd, even_odd_pairs
from interpreter.hlasm.opcodes.logical_add_subtract import (
    ADD_32 as ADD_LOGICAL_32,
)
from interpreter.hlasm.opcodes.logical_add_subtract import (
    ADD_64 as ADD_LOGICAL_64,
)
from interpreter.hlasm.opcodes.result_and_cc import Operation, apply_result_and_cc
from interpreter.hlasm.opcodes.signed_add_subtract import ADD_32, ADD_64
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.place import Place
from interpreter.hlasm.places import (
    in_storage,
    low_word,
    low_word_pair,
    register_pair,
    whole_register,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type RegisterPlace = Callable[[HlasmEmitter, int], Place]
type AfterStep = Callable[[HlasmEmitter, Register], None]

THIRD_REGISTER = 1
SWAPPED_OPERAND = 2
COMPARE_AND_LOAD_REGISTER = 0
FIRST_STORAGE = 1
SECOND_STORAGE = 2
QUADWORD_BYTES = 16
TEST_AND_SET_OPERAND = 0
ALL_ONES_BYTE = BYTE_MASK
LEFTMOST_BIT_SHIFT = 7


def _compare_and_swap(register: RegisterPlace, width: int) -> StatementLowering:
    address_of = aligned_storage_address_at(SWAPPED_OPERAND, width)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        second = in_storage(emitter, address_of(emitter, statement), width)
        first = register(emitter, reg_operand(statement, REGISTER_OPERAND))
        third = register(emitter, reg_operand(statement, THIRD_REGISTER))
        emit_compare_or_refresh(
            emitter,
            Comparison(first, second, first),
            lambda: second.write(third.read()),
        )

    return lower


def _load_aligned(
    emitter: HlasmEmitter, address: Register, width: int, target: Place
) -> None:
    emit_alignment_check(emitter, address, width)
    target.write(emitter.load_storage(address, 0, width))


def _compare_and_load(
    compared: RegisterPlace, loaded: RegisterPlace, widths: tuple[int, int]
) -> StatementLowering:
    first_width, second_width = widths
    first_of = aligned_storage_address_at(FIRST_STORAGE, first_width)
    second_of = storage_address_at(SECOND_STORAGE)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        first = in_storage(emitter, first_of(emitter, statement), first_width)
        second_address = second_of(emitter, statement)
        r3 = reg_operand(statement, COMPARE_AND_LOAD_REGISTER)
        third = loaded(emitter, r3)
        emit_compare_or_refresh(
            emitter,
            Comparison(compared(emitter, r3), first, third),
            lambda: _load_aligned(emitter, second_address, second_width, third),
        )

    return lower


def _store_both(
    second: Place, first: Place, original: Register
) -> Callable[[Register], None]:
    def store(result: Register) -> None:
        second.write(result)
        first.write(original)

    return store


def _load_and(
    operation: Operation,
    register: RegisterPlace,
    width: int,
    after: Sequence[AfterStep],
) -> StatementLowering:
    address_of = aligned_storage_address_at(SWAPPED_OPERAND, width)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        second = in_storage(emitter, address_of(emitter, statement), width)
        original = second.read()
        third = register(emitter, reg_operand(statement, THIRD_REGISTER)).read()
        first = register(emitter, reg_operand(statement, REGISTER_OPERAND))
        arguments = {PARAM_LEFT: original, PARAM_RIGHT: third}
        store = _store_both(second, first, original)
        cc = apply_result_and_cc(emitter, operation, arguments, store)
        _ = [step(emitter, cc) for step in after]

    return lower


def _connective(connective: BooleanConnective, bits: int) -> Operation:
    return build_boolean_cc_ir(f"hlasm.interlocked{bits}", bits, connective)


def _load_pair_disjoint(register: RegisterPlace, width: int) -> StatementLowering:
    operands = tuple(
        aligned_storage_address_at(index, width)
        for index in (FIRST_STORAGE, SECOND_STORAGE)
    )

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        addresses = [address_of(emitter, statement) for address_of in operands]
        values = [emitter.load_storage(address, 0, width) for address in addresses]
        r3 = reg_operand(statement, COMPARE_AND_LOAD_REGISTER)
        _ = [register(emitter, r3 + k).write(value) for k, value in enumerate(values)]
        emit_cc(emitter, EQUAL_CC)

    return even_odd(lower)


def lower_test_and_set(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    address = storage_address_at(TEST_AND_SET_OPERAND)(emitter, statement)
    byte = emitter.load_storage(address, 0, ONE_BYTE)
    emitter.store_storage(address, 0, ONE_BYTE, emitter.int_(ALL_ONES_BYTE))
    emitter.set_cc(
        emitter.binop(BinopKind.RSHIFT, byte, emitter.int_(LEFTMOST_BIT_SHIFT))
    )


COMPARE_AND_SWAP: Mapping[str, StatementLowering] = {
    "CS": _compare_and_swap(low_word, WORD_BYTES),
    "CSY": _compare_and_swap(low_word, WORD_BYTES),
    "CSG": _compare_and_swap(whole_register, DOUBLEWORD_BYTES),
    "CDS": even_odd_pairs(
        (REGISTER_OPERAND, THIRD_REGISTER),
        _compare_and_swap(low_word_pair, DOUBLEWORD_BYTES),
    ),
    "CDSY": even_odd_pairs(
        (REGISTER_OPERAND, THIRD_REGISTER),
        _compare_and_swap(low_word_pair, DOUBLEWORD_BYTES),
    ),
    "CDSG": even_odd_pairs(
        (REGISTER_OPERAND, THIRD_REGISTER),
        _compare_and_swap(register_pair, QUADWORD_BYTES),
    ),
    "CSST": lower_compare_and_swap_and_store,
}

COMPARE_AND_LOAD: Mapping[str, StatementLowering] = {
    "CAL": _compare_and_load(low_word, low_word, (WORD_BYTES, WORD_BYTES)),
    "CALGF": _compare_and_load(
        low_word, whole_register, (WORD_BYTES, DOUBLEWORD_BYTES)
    ),
    "CALG": _compare_and_load(
        whole_register, whole_register, (DOUBLEWORD_BYTES, DOUBLEWORD_BYTES)
    ),
}

OVERFLOW_CHECKED = (emit_fixed_point_overflow_check,)

LOAD_AND: Mapping[str, StatementLowering] = {
    "LAA": _load_and(ADD_32, low_word, WORD_BYTES, OVERFLOW_CHECKED),
    "LAAG": _load_and(ADD_64, whole_register, DOUBLEWORD_BYTES, OVERFLOW_CHECKED),
    "LAAL": _load_and(ADD_LOGICAL_32, low_word, WORD_BYTES, ()),
    "LAALG": _load_and(ADD_LOGICAL_64, whole_register, DOUBLEWORD_BYTES, ()),
    "LAN": _load_and(_connective(AND, WORD_BITS), low_word, WORD_BYTES, ()),
    "LANG": _load_and(
        _connective(AND, DOUBLEWORD_BITS), whole_register, DOUBLEWORD_BYTES, ()
    ),
    "LAO": _load_and(_connective(OR, WORD_BITS), low_word, WORD_BYTES, ()),
    "LAOG": _load_and(
        _connective(OR, DOUBLEWORD_BITS), whole_register, DOUBLEWORD_BYTES, ()
    ),
    "LAX": _load_and(_connective(XOR, WORD_BITS), low_word, WORD_BYTES, ()),
    "LAXG": _load_and(
        _connective(XOR, DOUBLEWORD_BITS), whole_register, DOUBLEWORD_BYTES, ()
    ),
}

LOAD_STORE_PAIR: Mapping[str, StatementLowering] = {
    "LPD": _load_pair_disjoint(low_word, WORD_BYTES),
    "LPDG": _load_pair_disjoint(whole_register, DOUBLEWORD_BYTES),
    "LPQ": even_odd(move(from_aligned_storage(QUADWORD_BYTES), (), to_doubleword_pair)),
    "STPQ": even_odd(
        move(from_doubleword_pair, (), to_aligned_storage(QUADWORD_BYTES))
    ),
}

INTERLOCKED_LOWERINGS: Mapping[str, StatementLowering] = {
    **COMPARE_AND_SWAP,
    **COMPARE_AND_LOAD,
    **LOAD_AND,
    **LOAD_STORE_PAIR,
    "TS": lower_test_and_set,
}
