# pyright: standard
"""An IR loop over the byte offsets 0 to length - 1 of a compile-time length, the offset kept in a variable."""

from collections.abc import Callable

from interpreter.hlasm.hlasm_constants import BYTE_LOOP_AT_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def _test_offset(
    emitter: HlasmEmitter, length: Register, step: CodeLabel, done: CodeLabel
) -> Register:
    at = emitter.load_var(BYTE_LOOP_AT_VAR)
    more = emitter.binop(BinopKind.LT, at, length)
    emitter.emit_inst(BranchIf(cond_reg=more, branch_targets=(step, done)))
    return at


def _advance(
    emitter: HlasmEmitter, at: Register, one: Register, loop: CodeLabel
) -> None:
    after = emitter.binop(BinopKind.ADD, at, one)
    emitter.emit_inst(StoreVar(name=BYTE_LOOP_AT_VAR, value_reg=after))
    emitter.emit_inst(Branch(label=loop))


def emit_byte_loop(
    emitter: HlasmEmitter, length: int, body: Callable[[Register], None]
) -> None:
    emitter.emit_inst(StoreVar(name=BYTE_LOOP_AT_VAR, value_reg=emitter.int_(0)))
    bound, one = emitter.int_(length), emitter.int_(1)
    loop, step, done = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_bytes_loop", "hl_bytes_step", "hl_bytes_done")
    )
    emitter.emit_inst(Label_(label=loop))
    at = _test_offset(emitter, bound, step, done)
    emitter.emit_inst(Label_(label=step))
    body(at)
    _advance(emitter, at, one, loop)
    emitter.emit_inst(Label_(label=done))
