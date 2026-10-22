# pyright: standard
"""Emits IR that runs only when a condition register is true, then rejoins."""

from collections.abc import Callable

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import BranchIf, Label_
from interpreter.register import Register


def emit_when(
    emitter: HlasmEmitter, condition: Register, then: Callable[[], None]
) -> None:
    taken, fall = emitter.fresh_label("hl_when"), emitter.fresh_label("hl_when_not")
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, fall)))
    emitter.emit_inst(Label_(label=taken))
    then()
    emitter.emit_inst(Label_(label=fall))
