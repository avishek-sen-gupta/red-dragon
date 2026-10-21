# pyright: standard
"""Register, storage, address and immediate moves composed of a source, transforms and a sink."""

from collections.abc import Callable, Sequence
from functools import reduce

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.alignment_check import emit_alignment_check
from interpreter.hlasm.effective_address import effective_address, relative_address
from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import (
    imm_operand,
    reg_operand,
    reloc_operand,
    storage_operand,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Source = Callable[[HlasmEmitter, MachineStatement], Register]
type Transform = Callable[[HlasmEmitter, Register], Register]
type Sink = Callable[[HlasmEmitter, MachineStatement, Register], None]

BYTE_MASK = 0xFF
LOW_WORD_MASK = 0xFFFFFFFF
REGISTER_MASK = 0xFFFFFFFF_FFFFFFFF
REGISTER_OPERAND = 0
SECOND_OPERAND = 1


def _ones(width: int) -> int:
    return (1 << (BITS_PER_BYTE * width)) - 1


def storage_address(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return effective_address(emitter, storage_operand(statement, SECOND_OPERAND))


def relative_target(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return relative_address(emitter, reloc_operand(statement, SECOND_OPERAND))


def _aligned(
    address: Callable[[HlasmEmitter, MachineStatement], Register], width: int
) -> Callable[[HlasmEmitter, MachineStatement], Register]:
    def checked(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
        at = address(emitter, statement)
        emit_alignment_check(emitter, at, width)
        return at

    return checked


def _load_from(
    address: Callable[[HlasmEmitter, MachineStatement], Register], width: int
) -> Source:
    def load(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
        return emitter.load_storage(address(emitter, statement), 0, width)

    return load


def _store_to(
    address: Callable[[HlasmEmitter, MachineStatement], Register], width: int
) -> Sink:
    def store(
        emitter: HlasmEmitter, statement: MachineStatement, value: Register
    ) -> None:
        emitter.store_storage(address(emitter, statement), 0, width, value)

    return store


def from_storage(width: int) -> Source:
    return _load_from(storage_address, width)


def from_aligned_storage(width: int) -> Source:
    return _load_from(_aligned(storage_address, width), width)


def from_relative(width: int) -> Source:
    return _load_from(_aligned(relative_target, width), width)


def to_storage(width: int) -> Sink:
    return _store_to(storage_address, width)


def to_relative(width: int) -> Sink:
    return _store_to(_aligned(relative_target, width), width)


def immediate(bits: int) -> Source:
    def image(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
        return emitter.int_(imm_operand(statement, SECOND_OPERAND) & ((1 << bits) - 1))

    return image


def from_gr32(index: int) -> Source:
    return lambda emitter, statement: emitter.load_gr32(reg_operand(statement, index))


def from_gr64(index: int) -> Source:
    return lambda emitter, statement: emitter.load_gr64(reg_operand(statement, index))


def to_gr32(
    emitter: HlasmEmitter, statement: MachineStatement, value: Register
) -> None:
    emitter.store_gr32(reg_operand(statement, REGISTER_OPERAND), value)


def to_gr64(
    emitter: HlasmEmitter, statement: MachineStatement, value: Register
) -> None:
    emitter.store_gr64(reg_operand(statement, REGISTER_OPERAND), value)


def merge_low_word(
    emitter: HlasmEmitter, r: int, inserted: Register, field_mask: int
) -> None:
    kept = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(r),
        emitter.int_(LOW_WORD_MASK & ~field_mask),
    )
    emitter.store_gr32(r, emitter.binop(BinopKind.BIT_OR, kept, inserted))


def into_bits(field_mask: int) -> Sink:
    def insert(
        emitter: HlasmEmitter, statement: MachineStatement, value: Register
    ) -> None:
        r = reg_operand(statement, REGISTER_OPERAND)
        kept = emitter.binop(
            BinopKind.BIT_AND,
            emitter.load_gr64(r),
            emitter.int_(REGISTER_MASK & ~field_mask),
        )
        emitter.store_gr64(r, emitter.binop(BinopKind.BIT_OR, kept, value))

    return insert


def into_low_bytes(width: int) -> Sink:
    def insert(
        emitter: HlasmEmitter, statement: MachineStatement, value: Register
    ) -> None:
        r = reg_operand(statement, REGISTER_OPERAND)
        merge_low_word(emitter, r, value, _ones(width))

    return insert


def signed(bits: int) -> Transform:
    half = 1 << (bits - 1)

    def extend(emitter: HlasmEmitter, value: Register) -> Register:
        biased = emitter.binop(BinopKind.ADD, value, emitter.int_(half))
        wrapped = emitter.binop(BinopKind.MOD, biased, emitter.int_(1 << bits))
        return emitter.binop(BinopKind.SUB, wrapped, emitter.int_(half))

    return extend


def shifted(bits: int) -> Transform:
    return lambda emitter, value: emitter.binop(
        BinopKind.LSHIFT, value, emitter.int_(bits)
    )


def keep(mask: int) -> Transform:
    return lambda emitter, value: emitter.binop(
        BinopKind.BIT_AND, value, emitter.int_(mask)
    )


def _byte_moved(
    emitter: HlasmEmitter, value: Register, moves: tuple[int, int]
) -> Register:
    source, target = moves
    shifted = emitter.binop(
        BinopKind.RSHIFT, value, emitter.int_(BITS_PER_BYTE * source)
    )
    byte = emitter.binop(BinopKind.BIT_AND, shifted, emitter.int_(BYTE_MASK))
    return emitter.binop(BinopKind.LSHIFT, byte, emitter.int_(BITS_PER_BYTE * target))


def gather_bytes(
    emitter: HlasmEmitter, value: Register, moves: Sequence[tuple[int, int]]
) -> Register:
    pieces = [_byte_moved(emitter, value, move) for move in moves]
    return reduce(
        lambda left, right: emitter.binop(BinopKind.BIT_OR, left, right),
        pieces[1:],
        pieces[0],
    )


def reversed_bytes(width: int) -> Transform:
    moves = tuple((at, width - 1 - at) for at in range(width))
    return lambda emitter, value: gather_bytes(emitter, value, moves)


def move(
    source: Source, transforms: Sequence[Transform], sink: Sink
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        value = reduce(
            lambda current, transform: transform(emitter, current),
            transforms,
            source(emitter, statement),
        )
        sink(emitter, statement, value)

    return lower
