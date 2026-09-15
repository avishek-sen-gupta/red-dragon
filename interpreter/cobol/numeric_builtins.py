# pyright: standard
"""COBOL builtins backed by the cobol_numeric exact-value boundary (red-dragon-4q25.1)."""

from __future__ import annotations

import math
from typing import Any

from cobol_numeric.number import from_float, is_cobol_number, to_plain_str
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.func_name import FuncName
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import Operators, VMState, _is_symbolic
from interpreter.vm.vm_types import BuiltinResult

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


def _builtin_cobol_to_text(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Text of a COBOL value: numbers render plainly (never exponent notation),
    so IS NUMERIC, DISPLAY and the encode path all see ``-?digits(.digits)?``."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if isinstance(value, str):
        return BuiltinResult(value=value)
    if isinstance(value, float) and math.isfinite(value):
        return BuiltinResult(value=to_plain_str(from_float(value)))
    if is_cobol_number(value):
        return BuiltinResult(value=to_plain_str(value))
    return BuiltinResult(value=str(value))


NUMERIC_BUILTINS: dict[FuncName, Any] = (
    {  # Any: Callable[(list[TypedValue], VMState) -> BuiltinResult] — builtin boundary
        FuncName(BuiltinName.COBOL_TO_TEXT): _builtin_cobol_to_text,
    }
)
