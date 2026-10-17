"""The size error test as IR: a result is a size error when its magnitude reaches the receiver's capacity."""

from __future__ import annotations

from cobol_numeric.number import CobolNumber
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register


def emit_size_error(e: IrEmitter, value: Register, capacity: CobolNumber) -> Register:
    number = e.call(BuiltinName.COBOL_PARSE_NUMBER, value)
    reaches_above = e.binop(">=", number, e.decimal(capacity))
    reaches_below = e.binop("<=", number, e.decimal(capacity.copy_negate()))
    return e.binop("or", reaches_above, reaches_below)
