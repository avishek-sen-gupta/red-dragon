# pyright: standard
"""COBOL builtins backed by the cobol_numeric exact-value boundary (red-dragon-4q25.1)."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from cobol_numeric.number import (
    add,
    as_whole_int,
    divide,
    from_float,
    is_cobol_number,
    multiply,
    subtract,
    to_float,
    to_number,
    to_plain_str,
)
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


def _exact_operation(
    operation: Callable[[Any, Any, int], Any],
) -> Callable[[list[TypedValue], VMState], BuiltinResult]:
    """Wrap an exact cobol_numeric operation as a builtin taking
    (left, right, result_decimals)."""

    def builtin(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
            return BuiltinResult(value=_UNCOMPUTABLE)
        if any(a.value is _UNCOMPUTABLE for a in args):
            return BuiltinResult(value=_UNCOMPUTABLE)
        decimals = args[2].value
        if isinstance(decimals, bool) or not isinstance(decimals, int):
            return BuiltinResult(value=_UNCOMPUTABLE)
        try:
            result = operation(
                to_number(args[0].value), to_number(args[1].value), decimals
            )
        except (ValueError, TypeError, ZeroDivisionError):
            return BuiltinResult(value=_UNCOMPUTABLE)
        whole = as_whole_int(result) if decimals == 0 else None
        return BuiltinResult(value=result if whole is None else whole)

    return builtin


def _builtin_cobol_to_float(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Operand of a floating-point expression (IBM rule) as an IEEE float."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if isinstance(value, float):
        return BuiltinResult(value=value)
    try:
        return BuiltinResult(value=to_float(to_number(value)))
    except (ValueError, TypeError):
        return BuiltinResult(value=_UNCOMPUTABLE)


NUMERIC_BUILTINS: dict[FuncName, Any] = (
    {  # Any: Callable[(list[TypedValue], VMState) -> BuiltinResult] — builtin boundary
        FuncName(BuiltinName.COBOL_TO_TEXT): _builtin_cobol_to_text,
        FuncName(BuiltinName.COBOL_ADD): _exact_operation(add),
        FuncName(BuiltinName.COBOL_SUBTRACT): _exact_operation(subtract),
        FuncName(BuiltinName.COBOL_MULTIPLY): _exact_operation(multiply),
        FuncName(BuiltinName.COBOL_DIVIDE): _exact_operation(divide),
        FuncName(BuiltinName.COBOL_TO_FLOAT): _builtin_cobol_to_float,
    }
)
