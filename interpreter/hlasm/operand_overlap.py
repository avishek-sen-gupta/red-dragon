# pyright: standard
"""Whether a destination starts inside the source bytes that take part in a move: the case where a left-to-right move reads bytes it has already stored."""

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def starts_inside_source(
    emitter: HlasmEmitter, addresses: tuple[Register, Register], length: Register
) -> Register:
    target, source = addresses
    source_end = emitter.binop(BinopKind.ADD, source, length)
    return emitter.binop(
        BinopKind.AND,
        emitter.binop(BinopKind.LT, source, target),
        emitter.binop(BinopKind.LT, target, source_end),
    )
