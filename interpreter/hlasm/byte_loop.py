# pyright: standard
"""An IR loop over offsets from a start to a bound by a fixed step, the offset kept in a variable; its constants are set before the loop, and a scan's body may branch out of it."""

from collections.abc import Callable

from interpreter.hlasm.hlasm_constants import BYTE_LOOP_AT_VAR, ONE_BYTE
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type LoopBody = Callable[[Register], None]


def _test_offset(
    emitter: HlasmEmitter, bound: Register, step: CodeLabel, done: CodeLabel
) -> Register:
    at = emitter.load_var(BYTE_LOOP_AT_VAR)
    more = emitter.binop(BinopKind.LT, at, bound)
    emitter.emit_inst(BranchIf(cond_reg=more, branch_targets=(step, done)))
    return at


def advance(
    emitter: HlasmEmitter, at: Register, stride: Register, loop: CodeLabel
) -> None:
    after = emitter.binop(BinopKind.ADD, at, stride)
    emitter.emit_inst(StoreVar(name=BYTE_LOOP_AT_VAR, value_reg=after))
    emitter.emit_inst(Branch(label=loop))


def emit_scan_loop[T](
    emitter: HlasmEmitter,
    span: tuple[Register, Register],
    step: int,
    body: Callable[[Register], T],
) -> tuple[Register, T]:
    start, bound = span
    stride = emitter.int_(step)
    emitter.emit_inst(StoreVar(name=BYTE_LOOP_AT_VAR, value_reg=start))
    loop, iteration, done = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_bytes_loop", "hl_bytes_step", "hl_bytes_done")
    )
    emitter.emit_inst(Label_(label=loop))
    at = _test_offset(emitter, bound, iteration, done)
    emitter.emit_inst(Label_(label=iteration))
    result = body(at)
    advance(emitter, at, stride, loop)
    emitter.emit_inst(Label_(label=done))
    return at, result


def emit_counted_loop(
    emitter: HlasmEmitter,
    span: tuple[Register, Register],
    step: int,
    body: LoopBody,
) -> None:
    emit_scan_loop(emitter, span, step, body)


def emit_byte_loop(emitter: HlasmEmitter, length: Register, body: LoopBody) -> None:
    span = (emitter.int_(0), length)
    emit_counted_loop(emitter, span, ONE_BYTE, body)


def copied_byte(
    emitter: HlasmEmitter, addresses: tuple[Register, Register], at: Register
) -> Register:
    target, source = addresses
    image = emitter.load_bytes(source, at, ONE_BYTE)
    emitter.write_bytes(target, at, ONE_BYTE, image)
    return image


def copy_byte(
    emitter: HlasmEmitter, addresses: tuple[Register, Register], at: Register
) -> None:
    copied_byte(emitter, addresses, at)
