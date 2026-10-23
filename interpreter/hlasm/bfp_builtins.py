# pyright: standard
"""The BFP arithmetic builtins over zarch_float; the "too cumbersome" clause: exact IEEE arithmetic in IR would dwarf the program."""

from collections.abc import Callable, Mapping, Sequence

from interpreter.func_name import FuncName
from interpreter.hlasm.bfp_fields import BfpFields, fields_of, value_of
from interpreter.hlasm.bfp_layout import (
    EXTENDED_LAYOUT,
    LONG_LAYOUT,
    SHORT_LAYOUT,
    BfpLayout,
)
from interpreter.hlasm.bfp_operation import BfpOperation, bfp_builtin_name
from interpreter.hlasm.ieee_words import ieee_words
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult
from zarch_float.bfp_arithmetic import (
    bfp_add,
    bfp_divide,
    bfp_multiply,
    bfp_multiply_add,
    bfp_multiply_subtract,
    bfp_square_root,
    bfp_subtract,
)
from zarch_float.bfp_convert import (
    bfp_from_integer,
    bfp_load_rounded,
    bfp_round_to_integral,
    bfp_to_integer,
    bfp_widened,
)
from zarch_float.bfp_divide_to_integer import bfp_divide_to_integer
from zarch_float.bfp_divide_to_integer_result import BfpDivideToIntegerResult
from zarch_float.bfp_result import BfpResult
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.float_kind import FloatKind
from zarch_float.integer_format import (
    SIGNED_32,
    SIGNED_64,
    UNSIGNED_32,
    UNSIGNED_64,
    IntegerFormat,
)
from zarch_float.integer_result import IntegerResult
from zarch_float.rounding_mode import BFP_MODIFIER_MODES, RoundingMode

type _Binary = Callable[[BfpValue, BfpValue, RoundingMode], BfpResult]
type _Fused = Callable[[BfpValue, BfpValue, BfpValue, RoundingMode], BfpResult]
type _Unary = Callable[[BfpValue, RoundingMode], BfpResult]

INVALID_CC = 3
UNREACHABLE_SCALED = (0, 0, 0)


def _outcome(result: BfpResult, cc: int) -> list[int]:
    return [
        *fields_of(result.value).as_list(),
        *fields_of(result.scaled).as_list(),
        *ieee_words(result.conditions, result.scaled_conditions),
        cc,
    ]


def _operand(arg: TypedValue, layout: BfpLayout) -> BfpValue:
    negative, biased_exponent, fraction = arg.value
    fields = BfpFields(bool(negative), int(biased_exponent), int(fraction))
    return value_of(fields, layout.format)


def _mode(arg: TypedValue) -> RoundingMode:
    return BFP_MODIFIER_MODES[int(arg.value)]


def _binary(rule: _Binary, layout: BfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a, b = args
        result = rule(_operand(a, layout), _operand(b, layout), _mode(mode))
        return BuiltinResult(value=_outcome(result, 0))

    return call


def _fused(rule: _Fused, layout: BfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a, b, c = args
        result = rule(
            _operand(a, layout), _operand(b, layout), _operand(c, layout), _mode(mode)
        )
        return BuiltinResult(value=_outcome(result, 0))

    return call


def _unary(rule: _Unary, layout: BfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a = args
        return BuiltinResult(value=_outcome(rule(_operand(a, layout), _mode(mode)), 0))

    return call


def _lengthened(source: BfpLayout, target: BfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        a, b = (bfp_widened(_operand(arg, source), target.format) for arg in args)
        product = bfp_multiply(a, b, RoundingMode.NEAREST_EVEN)
        return BuiltinResult(value=_outcome(product, 0))

    return call


def _integer_cc(a: BfpValue, result: IntegerResult) -> int:
    signed_cc = (a.kind is not FloatKind.ZERO) * (2 - a.negative)
    return INVALID_CC if Condition.INVALID in result.conditions else signed_cc


def _integer_outcome(a: BfpValue, result: IntegerResult, image: int) -> list[int]:
    return [
        image,
        0,
        0,
        *UNREACHABLE_SCALED,
        *ieee_words(result.conditions, frozenset()),
        _integer_cc(a, result),
    ]


def _to_integer(target: IntegerFormat, layout: BfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a = args
        operand = _operand(a, layout)
        result = bfp_to_integer(operand, target, _mode(mode))
        image = result.value & (target.maximum - target.minimum)
        return BuiltinResult(value=_integer_outcome(operand, result, image))

    return call


def _from_integer(layout: BfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, n = args
        result = bfp_from_integer(int(n.value), layout.format, _mode(mode))
        return BuiltinResult(value=_outcome(result, 0))

    return call


def _rounded_into(target: BfpLayout) -> _Unary:
    return lambda a, mode: bfp_load_rounded(a, target.format, mode)


def _divided_cc(divided: BfpDivideToIntegerResult) -> int:
    special = divided.quotient_overflow or divided.quotient.is_nan()
    return 2 * int(divided.partial) + int(special)


def _divide_to_integer(layout: BfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        quotient_mode, remainder_mode, a, b = args
        divided = bfp_divide_to_integer(
            _operand(a, layout),
            _operand(b, layout),
            _mode(quotient_mode),
            _mode(remainder_mode),
        )
        outcome = _outcome(divided.remainder, _divided_cc(divided))
        return BuiltinResult(value=[*outcome, *fields_of(divided.quotient).as_list()])

    return call


_ALL = (SHORT_LAYOUT, LONG_LAYOUT, EXTENDED_LAYOUT)
_SHORT_AND_LONG = (SHORT_LAYOUT, LONG_LAYOUT)

_BINARIES: Mapping[BfpOperation, _Binary] = {
    BfpOperation.ADD: bfp_add,
    BfpOperation.SUBTRACT: bfp_subtract,
    BfpOperation.MULTIPLY: bfp_multiply,
    BfpOperation.DIVIDE: bfp_divide,
}
_FUSEDS: Mapping[BfpOperation, _Fused] = {
    BfpOperation.MULTIPLY_ADD: bfp_multiply_add,
    BfpOperation.MULTIPLY_SUBTRACT: bfp_multiply_subtract,
}
_UNARIES: Mapping[BfpOperation, _Unary] = {
    BfpOperation.SQUARE_ROOT: bfp_square_root,
    BfpOperation.ROUND_TO_INTEGRAL: bfp_round_to_integral,
}


_INTEGER_FORMATS: Mapping[BfpOperation, IntegerFormat] = {
    BfpOperation.TO_FIXED_32: SIGNED_32,
    BfpOperation.TO_FIXED_64: SIGNED_64,
    BfpOperation.TO_LOGICAL_32: UNSIGNED_32,
    BfpOperation.TO_LOGICAL_64: UNSIGNED_64,
}
_ROUNDINGS = (
    (BfpOperation.ROUNDED_TO_SHORT, LONG_LAYOUT, SHORT_LAYOUT),
    (BfpOperation.ROUNDED_TO_SHORT, EXTENDED_LAYOUT, SHORT_LAYOUT),
    (BfpOperation.ROUNDED_TO_LONG, EXTENDED_LAYOUT, LONG_LAYOUT),
)


def bfp_builtins() -> Mapping[FuncName, Builtin]:
    return {
        **{
            bfp_builtin_name(op, layout): _to_integer(target, layout)
            for op, target in _INTEGER_FORMATS.items()
            for layout in _ALL
        },
        **{
            bfp_builtin_name(BfpOperation.FROM_FIXED, layout): _from_integer(layout)
            for layout in _SHORT_AND_LONG
        },
        **{
            bfp_builtin_name(op, source): _unary(_rounded_into(target), source)
            for op, source, target in _ROUNDINGS
        },
        **{
            bfp_builtin_name(op, layout): _binary(rule, layout)
            for op, rule in _BINARIES.items()
            for layout in _ALL
        },
        **{
            bfp_builtin_name(op, layout): _fused(rule, layout)
            for op, rule in _FUSEDS.items()
            for layout in _SHORT_AND_LONG
        },
        **{
            bfp_builtin_name(op, layout): _unary(rule, layout)
            for op, rule in _UNARIES.items()
            for layout in _ALL
        },
        **{
            bfp_builtin_name(
                BfpOperation.DIVIDE_TO_INTEGER, layout
            ): _divide_to_integer(layout)
            for layout in _SHORT_AND_LONG
        },
        bfp_builtin_name(BfpOperation.MULTIPLY_LENGTHENED, SHORT_LAYOUT): _lengthened(
            SHORT_LAYOUT, LONG_LAYOUT
        ),
        bfp_builtin_name(BfpOperation.MULTIPLY_LENGTHENED, LONG_LAYOUT): _lengthened(
            LONG_LAYOUT, EXTENDED_LAYOUT
        ),
    }
