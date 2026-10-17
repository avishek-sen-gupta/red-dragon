"""FUNCTION STANDARD-DEVIATION as IR: the square root of the population variance of its arguments."""

from __future__ import annotations

from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register


def emit_standard_deviation(e: IrEmitter, values: tuple[Register, ...]) -> Register:
    return e.call(BuiltinName.SQRT, e.call(BuiltinName.VARIANCE, *values))
