# pyright: standard
"""BIT EXTRACT and BIT DEPOSIT as one IR loop over a mask's one bits, right to left, at most 64 iterations; each moves one bit between the mask bit and a cursor that starts at 2^(64 - ones) and doubles."""

from collections.abc import Callable

from interpreter.hlasm.bit_counts import lowest_one, population
from interpreter.hlasm.hlasm_constants import (
    DOUBLEWORD_BITS,
    MASK_LOOP_CURSOR_VAR,
    MASK_LOOP_REST_VAR,
    MASK_LOOP_RESULT_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Branch, BranchIf, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from interpreter.var_name import VarName

type Positions = Callable[[Register, Register], tuple[Register, Register]]


def _set(emitter: HlasmEmitter, name: VarName, value: Register) -> None:
    emitter.emit_inst(StoreVar(name=name, value_reg=value))


def _start(emitter: HlasmEmitter, mask: Register) -> None:
    unused = emitter.binop(
        BinopKind.SUB, emitter.int_(DOUBLEWORD_BITS), population(emitter, mask)
    )
    cursor = emitter.binop(BinopKind.LSHIFT, emitter.int_(1), unused)
    _set(emitter, MASK_LOOP_REST_VAR, mask)
    _set(emitter, MASK_LOOP_RESULT_VAR, emitter.int_(0))
    _set(emitter, MASK_LOOP_CURSOR_VAR, cursor)


def _moved_bit(
    emitter: HlasmEmitter, value: Register, positions: tuple[Register, Register]
) -> Register:
    read_at, write_at = positions
    picked = emitter.binop(BinopKind.BIT_AND, value, read_at)
    hit = emitter.binop(BinopKind.FLOOR_DIV, picked, read_at)
    return emitter.binop(BinopKind.MUL, hit, write_at)


def _iteration(
    emitter: HlasmEmitter, value: Register, rest: Register, positions: Positions
) -> None:
    low = lowest_one(emitter, rest)
    cursor = emitter.load_var(MASK_LOOP_CURSOR_VAR)
    moved = _moved_bit(emitter, value, positions(low, cursor))
    result = emitter.load_var(MASK_LOOP_RESULT_VAR)
    _set(emitter, MASK_LOOP_RESULT_VAR, emitter.binop(BinopKind.BIT_OR, result, moved))
    _set(
        emitter,
        MASK_LOOP_CURSOR_VAR,
        emitter.binop(BinopKind.LSHIFT, cursor, emitter.int_(1)),
    )
    _set(emitter, MASK_LOOP_REST_VAR, emitter.binop(BinopKind.BIT_XOR, rest, low))


def _remaining(emitter: HlasmEmitter, step: CodeLabel, done: CodeLabel) -> Register:
    rest = emitter.load_var(MASK_LOOP_REST_VAR)
    more = emitter.binop(BinopKind.NE, rest, emitter.int_(0))
    emitter.emit_inst(BranchIf(cond_reg=more, branch_targets=(step, done)))
    emitter.emit_inst(Label_(label=step))
    return rest


def _bits_under_mask(
    positions: Positions,
) -> Callable[[HlasmEmitter, Register, Register], Register]:
    def loop(emitter: HlasmEmitter, value: Register, mask: Register) -> Register:
        _start(emitter, mask)
        top, step, done = (
            emitter.fresh_label(prefix)
            for prefix in ("hl_mask_loop", "hl_mask_step", "hl_mask_done")
        )
        emitter.emit_inst(Label_(label=top))
        _iteration(emitter, value, _remaining(emitter, step, done), positions)
        emitter.emit_inst(Branch(label=top))
        emitter.emit_inst(Label_(label=done))
        return emitter.load_var(MASK_LOOP_RESULT_VAR)

    return loop


extracted_bits = _bits_under_mask(lambda mask_bit, cursor: (mask_bit, cursor))
deposited_bits = _bits_under_mask(lambda mask_bit, cursor: (cursor, mask_bit))
