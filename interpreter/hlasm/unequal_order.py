# pyright: standard
"""Sets CC 1 when the first of two unequal byte images is the lower, else CC 2, then branches on."""

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FIRST_LOW_CC = 1
FIRST_HIGH_CC = 2


def emit_cc_constant(
    emitter: HlasmEmitter, cc: int, label: CodeLabel, then: CodeLabel
) -> None:
    emitter.emit_inst(Label_(label=label))
    emitter.set_cc(emitter.int_(cc))
    emitter.emit_inst(Branch(label=then))


def emit_unequal_order(
    emitter: HlasmEmitter, images: tuple[Register, Register], then: CodeLabel
) -> None:
    first, second = images
    low, high = emitter.fresh_label("hl_first_low"), emitter.fresh_label(
        "hl_first_high"
    )
    lower = emitter.binop(BinopKind.LT, first, second)
    emitter.emit_inst(BranchIf(cond_reg=lower, branch_targets=(low, high)))
    emit_cc_constant(emitter, FIRST_LOW_CC, low, then)
    emit_cc_constant(emitter, FIRST_HIGH_CC, high, then)
