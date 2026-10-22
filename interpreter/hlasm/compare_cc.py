# pyright: standard
"""The storage compares' and translates' condition codes: a constant CC on a branch, one CC for a loop run to its end and another for a branch out of it, and CC 1 or 2 from two unequal unsigned unit values."""

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

EQUAL_CC = 0
FIRST_LOW_CC = 1
FIRST_HIGH_CC = 2


def emit_cc_constant(
    emitter: HlasmEmitter, cc: int, label: CodeLabel, then: CodeLabel
) -> None:
    emitter.emit_inst(Label_(label=label))
    emitter.set_cc(emitter.int_(cc))
    emitter.emit_inst(Branch(label=then))


def emit_loop_exit_cc(
    emitter: HlasmEmitter, ccs: tuple[int, int], stopped: CodeLabel
) -> None:
    ended_cc, stopped_cc = ccs
    join = emitter.fresh_label("hl_exit_join")
    emitter.set_cc(emitter.int_(ended_cc))
    emitter.emit_inst(Branch(label=join))
    emit_cc_constant(emitter, stopped_cc, stopped, join)
    emitter.emit_inst(Label_(label=join))


def emit_unequal_order(
    emitter: HlasmEmitter, values: tuple[Register, Register], then: CodeLabel
) -> None:
    first, second = values
    low, high = emitter.fresh_label("hl_first_low"), emitter.fresh_label(
        "hl_first_high"
    )
    lower = emitter.binop(BinopKind.LT, first, second)
    emitter.emit_inst(BranchIf(cond_reg=lower, branch_targets=(low, high)))
    emit_cc_constant(emitter, FIRST_LOW_CC, low, then)
    emit_cc_constant(emitter, FIRST_HIGH_CC, high, then)
