# pyright: standard
"""Branches an unsigned int to the label of the first ascending bound it is below, or to a last label when it is below none."""

from collections.abc import Sequence

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Bound = tuple[int, CodeLabel]


def _below(emitter: HlasmEmitter, value: Register, bound: Bound) -> None:
    limit, target = bound
    above = emitter.fresh_label("hl_range_above")
    below = emitter.binop(BinopKind.LT, value, emitter.int_(limit))
    emitter.emit_inst(BranchIf(cond_reg=below, branch_targets=(target, above)))
    emitter.emit_inst(Label_(label=above))


def emit_range_dispatch(
    emitter: HlasmEmitter,
    value: Register,
    bounds: Sequence[Bound],
    otherwise: CodeLabel,
) -> None:
    _ = [_below(emitter, value, bound) for bound in bounds]
    emitter.emit_inst(Branch(label=otherwise))
