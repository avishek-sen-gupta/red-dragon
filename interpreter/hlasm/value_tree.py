# pyright: standard
"""Selects one block per run-time value by a binary tree of `<` tests over the values it can take; a switch rejoins after the block."""

from collections.abc import Callable, Sequence

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Leaf = Callable[[int], None]


def _emit_tree(
    emitter: HlasmEmitter, value: Register, values: Sequence[int], leaf: Leaf
) -> None:
    if len(values) == 1:
        leaf(values[0])
        return
    middle = len(values) // 2
    low, high = emitter.fresh_label("hl_tree_low"), emitter.fresh_label("hl_tree_high")
    below = emitter.binop(BinopKind.LT, value, emitter.int_(values[middle]))
    emitter.emit_inst(BranchIf(cond_reg=below, branch_targets=(low, high)))
    emitter.emit_inst(Label_(label=low))
    _emit_tree(emitter, value, values[:middle], leaf)
    emitter.emit_inst(Label_(label=high))
    _emit_tree(emitter, value, values[middle:], leaf)


def emit_value_switch(
    emitter: HlasmEmitter, value: Register, values: Sequence[int], leaf: Leaf
) -> None:
    join = emitter.fresh_label("hl_switched")

    def joined(selected: int) -> None:
        leaf(selected)
        emitter.emit_inst(Branch(label=join))

    _emit_tree(emitter, value, values, joined)
    emitter.emit_inst(Label_(label=join))
