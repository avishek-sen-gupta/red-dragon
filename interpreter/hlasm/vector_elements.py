# pyright: standard
"""Vector register elements: element i of size s is bytes i*s to i*s+s-1 of the register; a static index is checked at lowering, a run-time index is taken modulo the element count."""

from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_constants import (
    VECTOR_REGISTER_BYTES,
    VECTOR_REGISTERS_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def load_element(
    emitter: HlasmEmitter, v: int, size: ElementSize, index: int
) -> Register:
    return emitter.load_vr_part(v, size.width * index, size.width)


def store_element(
    emitter: HlasmEmitter, v: int, size: ElementSize, index: int, value: Register
) -> None:
    emitter.store_vr_part(v, size.width * index, size.width, value)


def _element_address(
    emitter: HlasmEmitter, v: int, size: ElementSize, index: Register
) -> Register:
    within = emitter.binop(BinopKind.MOD, index, emitter.int_(size.count))
    offset = emitter.binop(BinopKind.MUL, within, emitter.int_(size.width))
    register = emitter.binop(
        BinopKind.ADD,
        emitter.load_var(VECTOR_REGISTERS_VAR),
        emitter.int_(VECTOR_REGISTER_BYTES * v),
    )
    return emitter.binop(BinopKind.ADD, register, offset)


def load_element_at(
    emitter: HlasmEmitter, v: int, size: ElementSize, index: Register
) -> Register:
    return emitter.load_storage(
        _element_address(emitter, v, size, index), 0, size.width
    )


def store_element_at(
    emitter: HlasmEmitter,
    v: int,
    size: ElementSize,
    index: Register,
    value: Register,
) -> None:
    emitter.store_storage(
        _element_address(emitter, v, size, index), 0, size.width, value
    )
