"""The labels one PERFORM VARYING loop branches between."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.emit_context import EmitContext
from interpreter.ir import CodeLabel


@dataclass(frozen=True)
class VaryingLabels:
    """One test and one step label per VARYING/AFTER level, outermost first."""

    tests: tuple[CodeLabel, ...]
    steps: tuple[CodeLabel, ...]
    body: CodeLabel
    exit: CodeLabel


def fresh_varying_labels(ctx: EmitContext, levels: int) -> VaryingLabels:
    return VaryingLabels(
        tests=tuple(ctx.fresh_label("pv_test") for _ in range(levels)),
        steps=tuple(ctx.fresh_label("pv_incr") for _ in range(levels)),
        body=ctx.fresh_label("pv_body"),
        exit=ctx.fresh_label("pv_exit"),
    )
