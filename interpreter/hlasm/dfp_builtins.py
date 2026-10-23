# pyright: standard
"""The DFP builtins over zarch_float; the "too cumbersome" clause: rounding to a preferred quantum by eight methods, in IR, would dwarf the program."""

from collections.abc import Callable, Mapping, Sequence

from interpreter.func_name import FuncName
from interpreter.hlasm.dfp_fields import dfp_fields_of, dfp_value_of
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.dfp_operation import DfpOperation, dfp_builtin_name
from interpreter.hlasm.ieee_words import ieee_words
from interpreter.hlasm.integer_outcome import integer_outcome, sign_cc
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult
from zarch_float.dfp_arithmetic import (
    dfp_add,
    dfp_divide,
    dfp_multiply,
    dfp_quantize,
    dfp_reround,
    dfp_subtract,
)
from zarch_float.dfp_convert import (
    dfp_from_integer,
    dfp_round_to_integral,
    dfp_to_integer,
)
from zarch_float.dfp_result import DfpResult
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind
from zarch_float.integer_format import (
    SIGNED_32,
    SIGNED_64,
    UNSIGNED_32,
    UNSIGNED_64,
    IntegerFormat,
)
from zarch_float.rounding_mode import DFP_MODIFIER_MODES, RoundingMode

type _Binary = Callable[[DfpValue, DfpValue, RoundingMode], DfpResult]


def _outcome(result: DfpResult) -> list[int]:
    return [
        *dfp_fields_of(result.value),
        *dfp_fields_of(result.scaled),
        *ieee_words(result.conditions, result.scaled_conditions),
        0,
    ]


def _operand(arg: TypedValue, layout: DfpLayout) -> DfpValue:
    return dfp_value_of([int(field) for field in arg.value], layout.format)


def _mode(arg: TypedValue) -> RoundingMode:
    return DFP_MODIFIER_MODES[int(arg.value)]


def _binary(rule: _Binary, layout: DfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a, b = args
        result = rule(_operand(a, layout), _operand(b, layout), _mode(mode))
        return BuiltinResult(value=_outcome(result))

    return call


def _reround(layout: DfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a, significance = args
        result = dfp_reround(_operand(a, layout), int(significance.value), _mode(mode))
        return BuiltinResult(value=_outcome(result))

    return call


def _integral(layout: DfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a = args
        result = dfp_round_to_integral(_operand(a, layout), _mode(mode))
        return BuiltinResult(value=_outcome(result))

    return call


def _from_integer(layout: DfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, n = args
        result = dfp_from_integer(int(n.value), layout.format, _mode(mode))
        return BuiltinResult(value=_outcome(result))

    return call


def _to_integer(target: IntegerFormat, layout: DfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a = args
        operand = _operand(a, layout)
        result = dfp_to_integer(operand, target, _mode(mode))
        source_cc = sign_cc(operand.kind is FloatKind.ZERO, operand.negative)
        return BuiltinResult(value=integer_outcome(source_cc, result, target))

    return call


_BINARIES: Mapping[DfpOperation, _Binary] = {
    DfpOperation.ADD: dfp_add,
    DfpOperation.SUBTRACT: dfp_subtract,
    DfpOperation.MULTIPLY: dfp_multiply,
    DfpOperation.DIVIDE: dfp_divide,
    DfpOperation.QUANTIZE: dfp_quantize,
}
_LAYOUTS = (LONG_DFP, EXTENDED_DFP)
_INTEGER_FORMATS: Mapping[DfpOperation, IntegerFormat] = {
    DfpOperation.TO_FIXED_32: SIGNED_32,
    DfpOperation.TO_FIXED_64: SIGNED_64,
    DfpOperation.TO_LOGICAL_32: UNSIGNED_32,
    DfpOperation.TO_LOGICAL_64: UNSIGNED_64,
}


def dfp_builtins() -> Mapping[FuncName, Builtin]:
    return {
        **{
            dfp_builtin_name(op, layout): _binary(rule, layout)
            for op, rule in _BINARIES.items()
            for layout in _LAYOUTS
        },
        **{
            dfp_builtin_name(DfpOperation.REROUND, layout): _reround(layout)
            for layout in _LAYOUTS
        },
        **{
            dfp_builtin_name(DfpOperation.ROUND_TO_INTEGRAL, layout): _integral(layout)
            for layout in _LAYOUTS
        },
        **{
            dfp_builtin_name(DfpOperation.FROM_FIXED, layout): _from_integer(layout)
            for layout in _LAYOUTS
        },
        **{
            dfp_builtin_name(op, layout): _to_integer(target, layout)
            for op, target in _INTEGER_FORMATS.items()
            for layout in _LAYOUTS
        },
    }
