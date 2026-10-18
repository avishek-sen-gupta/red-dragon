"""FUNCTION CHAR and ORD as IR: positions in the program collating sequence, counted from 1."""

from __future__ import annotations

from interpreter.cobol.cobol_constants import BuiltinName, CobolEncoding
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register


def emit_char(e: IrEmitter, args: tuple[Register, ...]) -> Register:
    position = e.binop("-", e.call(BuiltinName.INTEGER, args[0]), e.int_(1))
    characters = e.texts(e.ctx.collating_sequence.characters_by_position())
    return e.call(BuiltinName.LIST_GET, characters, position)


def emit_ord(e: IrEmitter, args: tuple[Register, ...]) -> Register:
    native, positions = e.ctx.collating_sequence.ordinal_alphabets()
    position_coded = e.call(
        BuiltinName.STRING_CONVERT, args[0], e.text(native), e.text(positions)
    )
    codes = e.call(
        BuiltinName.STRING_TO_BYTES, position_coded, e.text(CobolEncoding.LATIN1)
    )
    return e.binop("+", e.call(BuiltinName.LIST_GET, codes, e.int_(0)), e.int_(1))
