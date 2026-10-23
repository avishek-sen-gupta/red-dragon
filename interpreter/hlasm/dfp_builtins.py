# pyright: standard
"""The DFP builtins over zarch_float; the "too cumbersome" clause: rounding to a preferred quantum by eight methods and aligning coefficients across exponents thousands apart, in IR, would dwarf the program."""

from collections.abc import Callable, Mapping, Sequence

from interpreter.func_name import FuncName
from interpreter.hlasm.dfp_fields import dfp_fields_of, dfp_value_of
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.dfp_operation import DfpOperation, dfp_builtin_name
from interpreter.hlasm.ieee_words import ieee_words
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult
from zarch_float.comparison_result import ComparisonResult
from zarch_float.dfp_arithmetic import (
    dfp_add,
    dfp_compare,
    dfp_compare_signaling,
    dfp_divide,
    dfp_multiply,
    dfp_quantize,
    dfp_reround,
    dfp_subtract,
)
from zarch_float.dfp_convert import dfp_round_to_integral
from zarch_float.dfp_result import DfpResult
from zarch_float.dfp_value import DfpValue
from zarch_float.rounding_mode import DFP_MODIFIER_MODES, RoundingMode

type _Binary = Callable[[DfpValue, DfpValue, RoundingMode], DfpResult]
type _Compare = Callable[[DfpValue, DfpValue], ComparisonResult]

NO_FIELDS = (0, 0, 0)


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


def _compare(rule: _Compare, layout: DfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        a, b = args
        compared = rule(_operand(a, layout), _operand(b, layout))
        words = ieee_words(compared.conditions, frozenset())
        return BuiltinResult(
            value=[*NO_FIELDS, *NO_FIELDS, *words, compared.comparison.value]
        )

    return call


_BINARIES: Mapping[DfpOperation, _Binary] = {
    DfpOperation.ADD: dfp_add,
    DfpOperation.SUBTRACT: dfp_subtract,
    DfpOperation.MULTIPLY: dfp_multiply,
    DfpOperation.DIVIDE: dfp_divide,
    DfpOperation.QUANTIZE: dfp_quantize,
}
_COMPARES: Mapping[DfpOperation, _Compare] = {
    DfpOperation.COMPARE: dfp_compare,
    DfpOperation.COMPARE_SIGNALING: dfp_compare_signaling,
}
_LAYOUTS = (LONG_DFP, EXTENDED_DFP)


def dfp_builtins() -> Mapping[FuncName, Builtin]:
    return {
        **{
            dfp_builtin_name(op, layout): _binary(rule, layout)
            for op, rule in _BINARIES.items()
            for layout in _LAYOUTS
        },
        **{
            dfp_builtin_name(op, layout): _compare(rule, layout)
            for op, rule in _COMPARES.items()
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
    }
