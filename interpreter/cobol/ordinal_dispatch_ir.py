"""Branch to the n-th of a list of labels on an ordinal held in a register."""

from __future__ import annotations

from collections.abc import Sequence

from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.ir import CodeLabel
from interpreter.register import Register


def emit_ordinal_dispatch(
    emitter: IrEmitter, ordinal: Register, targets: Sequence[CodeLabel]
) -> None:
    """Ordinal k (1-based) branches to targets[k-1]; any other value falls
    through."""
    _ = [
        _emit_ordinal_case(emitter, ordinal, (k, target))
        for k, target in enumerate(targets, start=1)
    ]


def _emit_ordinal_case(
    emitter: IrEmitter, ordinal: Register, case: tuple[int, CodeLabel]
) -> None:
    k, target = case
    matched = emitter.binop("==", ordinal, emitter.int_(k))
    match_lbl = emitter.label("goto_dep_match")
    next_lbl = emitter.label("goto_dep_next")
    emitter.branch_if(matched, match_lbl, next_lbl)
    emitter.place(match_lbl)
    emitter.jump(target)
    emitter.place(next_lbl)
