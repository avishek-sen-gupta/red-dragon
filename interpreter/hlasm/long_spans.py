# pyright: standard
"""Walks two long operands left to right a unit at a time: the units both hold, then the longer operand's tail against the pad; the offset is left in the byte-loop variable."""

from collections.abc import Callable

from interpreter.hlasm.byte_loop import emit_counted_loop
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_operands import LongOperands
from interpreter.hlasm.long_registers import Pad
from interpreter.hlasm.unit_value import UnitReader, unit_reader
from interpreter.instructions import Branch, BranchIf, Label_
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type UnitBody = Callable[[Register, Register, Register], None]


def _common_units(
    emitter: HlasmEmitter,
    operands: LongOperands,
    unit: tuple[UnitReader, int],
    body: UnitBody,
) -> None:
    read, width = unit
    emit_counted_loop(
        emitter,
        (emitter.int_(0), operands.shorter),
        width,
        lambda at: body(at, read(operands.first, at), read(operands.second, at)),
    )


def _tails(
    emitter: HlasmEmitter,
    operands: LongOperands,
    pad: tuple[UnitReader, Register, int],
    body: UnitBody,
) -> None:
    read, value, width = pad
    first_tail, second_tail, done = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_span_first", "hl_span_second", "hl_span_done")
    )
    first_longer = emitter.binop(
        BinopKind.LT, operands.second_length, operands.first_length
    )
    emitter.emit_inst(
        BranchIf(cond_reg=first_longer, branch_targets=(first_tail, second_tail))
    )
    emitter.emit_inst(Label_(label=first_tail))
    emit_counted_loop(
        emitter,
        (operands.shorter, operands.first_length),
        width,
        lambda at: body(at, read(operands.first, at), value),
    )
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=second_tail))
    emit_counted_loop(
        emitter,
        (operands.shorter, operands.second_length),
        width,
        lambda at: body(at, value, read(operands.second, at)),
    )
    emitter.emit_inst(Label_(label=done))


def walk_spans(
    emitter: HlasmEmitter, operands: LongOperands, pad: Pad, body: UnitBody
) -> None:
    value, width = pad
    read = unit_reader(emitter, width)
    _common_units(emitter, operands, (read, width), body)
    _tails(emitter, operands, (read, value, width), body)
