# pyright: standard
"""Emits IR that runs only when a condition register is true, or one of two blocks by it, then rejoins; or picks one of two values by a 0/1 condition without branching."""

from collections.abc import Callable

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def emit_when(
    emitter: HlasmEmitter, condition: Register, then: Callable[[], None]
) -> None:
    taken, fall = emitter.fresh_label("hl_when"), emitter.fresh_label("hl_when_not")
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, fall)))
    emitter.emit_inst(Label_(label=taken))
    then()
    emitter.emit_inst(Label_(label=fall))


def emit_either(
    emitter: HlasmEmitter,
    condition: Register,
    then: Callable[[], None],
    otherwise: Callable[[], None],
) -> None:
    taken, fall = emitter.fresh_label("hl_then"), emitter.fresh_label("hl_else")
    join = emitter.fresh_label("hl_either")
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, fall)))
    emitter.emit_inst(Label_(label=taken))
    then()
    emitter.emit_inst(Branch(label=join))
    emitter.emit_inst(Label_(label=fall))
    otherwise()
    emitter.emit_inst(Label_(label=join))


def pick(
    emitter: HlasmEmitter, chosen: Register, then: Register, otherwise: Register
) -> Register:
    difference = emitter.binop(BinopKind.SUB, then, otherwise)
    taken = emitter.binop(BinopKind.MUL, chosen, difference)
    return emitter.binop(BinopKind.ADD, otherwise, taken)
