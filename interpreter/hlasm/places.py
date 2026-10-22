# pyright: standard
"""Places for interlocked operands: a register's low word or whole value, an even-odd pair as one value, storage at an address or an offset from it, storage at an address held in a doubleword, and a register numbered at run time."""

from interpreter.hlasm.alignment_check import emit_alignment_check
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    BINARY_BYTES_TO_INT,
    BITS_PER_BYTE,
    DOUBLEWORD_BITS,
    DOUBLEWORD_BYTES,
    GPR_BYTES,
    GPRS_VAR,
    WORD_BITS,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.place import Place
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def low_word(emitter: HlasmEmitter, r: int) -> Place:
    return Place(
        lambda: emitter.load_gr32(r), lambda value: emitter.store_gr32(r, value)
    )


def whole_register(emitter: HlasmEmitter, r: int) -> Place:
    return Place(
        lambda: emitter.load_gr64(r), lambda value: emitter.store_gr64(r, value)
    )


def joined(emitter: HlasmEmitter, halves: tuple[Place, Place], bits: int) -> Place:
    high, low = halves

    def read() -> Register:
        shifted = emitter.binop(BinopKind.LSHIFT, high.read(), emitter.int_(bits))
        return emitter.binop(BinopKind.BIT_OR, shifted, low.read())

    def write(value: Register) -> None:
        high.write(emitter.binop(BinopKind.RSHIFT, value, emitter.int_(bits)))
        low.write(value)

    return Place(read, write)


def in_storage(emitter: HlasmEmitter, address: Register, width: int) -> Place:
    return at_offset(emitter, address, 0, width)


def held_address(
    emitter: HlasmEmitter, holder: Register, offset: int, boundary: int
) -> Register:
    held = emitter.load_storage(holder, offset, DOUBLEWORD_BYTES)
    address = emitter.binop(BinopKind.BIT_AND, held, emitter.int_(ADDRESS_MASK_31))
    emit_alignment_check(emitter, address, boundary)
    return address


def at_offset(emitter: HlasmEmitter, base: Register, offset: int, width: int) -> Place:
    return Place(
        lambda: emitter.load_storage(base, offset, width),
        lambda value: emitter.store_storage(base, offset, width, value),
    )


def low_word_pair(emitter: HlasmEmitter, r: int) -> Place:
    return joined(emitter, (low_word(emitter, r), low_word(emitter, r + 1)), WORD_BITS)


def register_pair(emitter: HlasmEmitter, r: int) -> Place:
    halves = (whole_register(emitter, r), whole_register(emitter, r + 1))
    return joined(emitter, halves, DOUBLEWORD_BITS)


def _register_offset(emitter: HlasmEmitter, r: Register, width: int) -> Register:
    scaled = emitter.binop(BinopKind.MUL, r, emitter.int_(GPR_BYTES))
    return emitter.binop(BinopKind.ADD, scaled, emitter.int_(GPR_BYTES - width))


def numbered_register(emitter: HlasmEmitter, r: Register, width: int) -> Place:
    def read() -> Register:
        offset = _register_offset(emitter, r, width)
        image = emitter.load_bytes(emitter.load_var(GPRS_VAR), offset, width)
        return emitter.call(BINARY_BYTES_TO_INT, (image, emitter.unsigned_flag()))

    def write(value: Register) -> None:
        wrapped = emitter.binop(
            BinopKind.MOD, value, emitter.int_(1 << (BITS_PER_BYTE * width))
        )
        offset = _register_offset(emitter, r, width)
        image = emitter.image(wrapped, width)
        emitter.write_bytes(emitter.load_var(GPRS_VAR), offset, width, image)

    return Place(read, write)
