"""STRING's transfer as IR (ANSI X3.23-1985 STRING general rules).

The delimited sendings are moved one character at a time into the receiver,
starting at the pointer. The overflow condition arises when the pointer is
below 1 or past the receiver before the transfer, or when characters remain
once the receiver is full. Characters the transfer does not reach keep their
value, and the pointer advances by the characters moved. Each sending is moved
in turn, so the characters before a sending whose value is unknown stay known.
"""

from __future__ import annotations

from collections.abc import Sequence

from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.string_ir_outcome import StringIrOutcome
from interpreter.register import Register
from interpreter.var_name import VarName


def emit_string(
    e: IrEmitter, receiver: Register, pointer: Register, parts: Sequence[Register]
) -> StringIrOutcome:
    """The receiver's characters, the pointer and the overflow condition after
    the delimited ``parts`` are moved into ``receiver`` from ``pointer``."""
    size = e.call(BuiltinName.LENGTH, receiver)
    state = (
        e.var("string_image", receiver),
        e.var("string_pointer", pointer),
        e.var("string_overflow", e.bool_(True)),
    )
    done = e.label("string_done")
    e.skip_if(e.binop("<", pointer, e.int_(1)), done)
    e.skip_if(e.binop(">", pointer, size), done)
    e.store(state[2], e.bool_(False))
    for part in parts:
        _move(e, state, size, part)
    e.place(done)
    image, moved_to, overflow = state
    return StringIrOutcome(
        image=e.load(image), pointer=e.load(moved_to), overflow=e.load(overflow)
    )


def _move(
    e: IrEmitter,
    state: tuple[VarName, VarName, VarName],
    size: Register,
    part: Register,
) -> None:
    """Move as much of ``part`` as the receiver has room for; overflow when
    some of it does not fit."""
    image, pointer, overflow = state
    at = e.binop("-", e.load(pointer), e.int_(1))
    taken = e.call(BuiltinName.STRING_SLICE, part, e.int_(0), e.binop("-", size, at))
    count = e.call(BuiltinName.LENGTH, taken)
    e.store(image, e.call(BuiltinName.STRING_SPLICE, e.load(image), at, count, taken))
    e.store(pointer, e.binop("+", e.load(pointer), count))
    _note_overflow(e, overflow, (count, part))


def _note_overflow(
    e: IrEmitter, overflow: VarName, moved: tuple[Register, Register]
) -> None:
    """Overflow when fewer characters were moved than the part has."""
    count, part = moved
    fitted = e.label("string_fitted")
    e.skip_if(e.binop(">=", count, e.call(BuiltinName.LENGTH, part)), fitted)
    e.store(overflow, e.bool_(True))
    e.place(fitted)
