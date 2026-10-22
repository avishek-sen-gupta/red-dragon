# pyright: standard
"""An operand address off its boundary is a specification exception: the run abends S0C6."""

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def emit_alignment_check(
    emitter: HlasmEmitter, address: Register, boundary: int
) -> None:
    offset = emitter.binop(BinopKind.BIT_AND, address, emitter.int_(boundary - 1))
    emit_specification_check(
        emitter, emitter.binop(BinopKind.NE, offset, emitter.int_(0))
    )
