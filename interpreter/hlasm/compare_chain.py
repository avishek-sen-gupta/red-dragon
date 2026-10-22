# pyright: standard
"""Interlocked comparisons in order: the first unequal one replaces its place with the operand and leaves; when all are equal the equal path runs."""

from collections.abc import Callable, Sequence
from functools import partial

from interpreter.hlasm.comparison import Comparison
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind

type Unequal = Callable[[int], None]

EQUAL_CC = 0
UNEQUAL_CC = 1


def _compared(
    emitter: HlasmEmitter,
    comparison: Comparison,
    unequal: Callable[[], None],
    done: CodeLabel,
) -> None:
    value, operand = comparison.value.read(), comparison.operand.read()
    differ = emitter.binop(BinopKind.NE, value, operand)
    missed, matched = emitter.fresh_label("hl_unequal"), emitter.fresh_label("hl_equal")
    emitter.emit_inst(BranchIf(cond_reg=differ, branch_targets=(missed, matched)))
    emitter.emit_inst(Label_(label=missed))
    comparison.refreshed.write(operand)
    unequal()
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=matched))


def emit_compare_chain(
    emitter: HlasmEmitter,
    comparisons: Sequence[Comparison],
    unequal: Unequal,
    equal: Callable[[], None],
) -> None:
    done = emitter.fresh_label("hl_compared")
    _ = [
        _compared(emitter, comparison, partial(unequal, k), done)
        for k, comparison in enumerate(comparisons)
    ]
    equal()
    emitter.emit_inst(Label_(label=done))


def emit_cc(emitter: HlasmEmitter, cc: int) -> None:
    emitter.set_cc(emitter.int_(cc))


def emit_compare_or_refresh(
    emitter: HlasmEmitter, comparison: Comparison, equal: Callable[[], None]
) -> None:
    def matched() -> None:
        equal()
        emit_cc(emitter, EQUAL_CC)

    emit_compare_chain(
        emitter, (comparison,), lambda _: emit_cc(emitter, UNEQUAL_CC), matched
    )
