# pyright: standard
"""The register pairs of the long moves, compares and translates: their addresses, lengths and pads read before anything is stored, the even-length checks, and the addresses stored or advanced and lengths counted down at completion."""

from collections.abc import Callable

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import effective_address, register_address
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    BYTE_MASK,
    LOW_WORD_MASK,
    ONE_BYTE,
    WORD_BITS,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_operands import LongOperands
from interpreter.hlasm.operands import reg_operand, storage_operand
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Pad = tuple[Register, int]
type Pairs = tuple[int, int]
type LengthCheck = Callable[[HlasmEmitter, LongOperands], None]

LONG_LENGTH = 0xFFFFFF
REGISTER_PAD_SHIFT = 24
PAD_OPERAND = 2
ODD_LENGTH = 1


def operand_pairs(statement: MachineStatement) -> Pairs:
    return reg_operand(statement, FIRST_OPERAND), reg_operand(statement, SECOND_OPERAND)


def smaller(emitter: HlasmEmitter, left: Register, right: Register) -> Register:
    difference = emitter.binop(BinopKind.SUB, left, right)
    borrow = emitter.binop(BinopKind.RSHIFT, difference, emitter.int_(WORD_BITS))
    shortfall = emitter.binop(BinopKind.BIT_AND, difference, borrow)
    return emitter.binop(BinopKind.ADD, right, shortfall)


def _length(emitter: HlasmEmitter, r: int, length_mask: int) -> Register:
    return emitter.binop(
        BinopKind.BIT_AND, emitter.load_gr32(r + 1), emitter.int_(length_mask)
    )


def long_operands(
    emitter: HlasmEmitter, pairs: Pairs, length_mask: int
) -> LongOperands:
    first, second = pairs
    first_length = _length(emitter, first, length_mask)
    second_length = _length(emitter, second, length_mask)
    return LongOperands(
        register_address(emitter, first),
        first_length,
        register_address(emitter, second),
        second_length,
        smaller(emitter, first_length, second_length),
    )


def store_address(emitter: HlasmEmitter, r: int, address: Register) -> None:
    emitter.store_gr32(r, emitter.masked_address(address))


def store_progress(
    emitter: HlasmEmitter, r: int, address: Register, remaining: Register
) -> None:
    store_address(emitter, r, address)
    emitter.store_gr32(r + 1, remaining)


def advance_address(
    emitter: HlasmEmitter, r: int, address: Register, count: Register
) -> None:
    store_address(emitter, r, emitter.binop(BinopKind.ADD, address, count))


def count_down(
    emitter: HlasmEmitter, r: int, remaining: Register, length_mask: int
) -> None:
    kept = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(r + 1),
        emitter.int_(LOW_WORD_MASK & ~length_mask),
    )
    emitter.store_gr32(r + 1, emitter.binop(BinopKind.BIT_OR, kept, remaining))


def advance_operand(
    emitter: HlasmEmitter,
    r: int,
    operand: tuple[Register, Register, Register],
    compared: Register,
    length_mask: int,
) -> None:
    address, length, written = operand
    advanced = smaller(emitter, compared, length)
    advance_address(emitter, r, address, advanced)
    count_down(emitter, r, emitter.binop(BinopKind.SUB, written, advanced), length_mask)


def advance_operands(
    emitter: HlasmEmitter,
    pairs: Pairs,
    operands: LongOperands,
    progress: tuple[tuple[Register, Register], Register],
    length_mask: int,
) -> None:
    written, compared = progress
    advance_operand(
        emitter,
        pairs[0],
        (operands.first, operands.first_length, written[0]),
        compared,
        length_mask,
    )
    advance_operand(
        emitter,
        pairs[1],
        (operands.second, operands.second_length, written[1]),
        compared,
        length_mask,
    )


def register_pad(emitter: HlasmEmitter, second: int) -> Pad:
    shifted = emitter.binop(
        BinopKind.RSHIFT,
        emitter.load_gr32(second + 1),
        emitter.int_(REGISTER_PAD_SHIFT),
    )
    return emitter.binop(BinopKind.BIT_AND, shifted, emitter.int_(BYTE_MASK)), ONE_BYTE


def address_pad(emitter: HlasmEmitter, statement: MachineStatement, width: int) -> Pad:
    address = effective_address(emitter, storage_operand(statement, PAD_OPERAND))
    pad = emitter.binop(
        BinopKind.BIT_AND,
        address,
        emitter.int_((1 << (BITS_PER_BYTE * width)) - 1),
    )
    return pad, width


def no_length_check(emitter: HlasmEmitter, operands: LongOperands) -> None:
    return


def even_length(emitter: HlasmEmitter, length: Register) -> None:
    odd = emitter.binop(BinopKind.BIT_AND, length, emitter.int_(ODD_LENGTH))
    emit_specification_check(emitter, emitter.binop(BinopKind.NE, odd, emitter.int_(0)))


def unit_length(emitter: HlasmEmitter, r: int, width: int) -> Register:
    length = emitter.load_gr32(r + 1)
    if width > ONE_BYTE:
        even_length(emitter, length)
    return length


def even_lengths(emitter: HlasmEmitter, operands: LongOperands) -> None:
    even_length(
        emitter,
        emitter.binop(BinopKind.BIT_OR, operands.first_length, operands.second_length),
    )
