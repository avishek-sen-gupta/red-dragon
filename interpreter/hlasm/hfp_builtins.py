# pyright: standard
"""The HFP arithmetic and rounding conversion builtins over zarch_float; the "too cumbersome" clause: guard-digit alignment, normalization, exact products, quotients and roots of up to 28 hexadecimal digits, and rounding by a method into fixed point or BFP, in IR would dwarf the program."""

from collections.abc import Callable, Mapping, Sequence

from interpreter.func_name import FuncName
from interpreter.hlasm.bfp_fields import fields_of
from interpreter.hlasm.bfp_layout import LONG_LAYOUT as LONG_BFP
from interpreter.hlasm.bfp_layout import SHORT_LAYOUT as SHORT_BFP
from interpreter.hlasm.bfp_layout import BfpLayout
from interpreter.hlasm.hfp_layout import (
    CHARACTERISTIC_MASK,
    EXCESS,
    EXTENDED_HFP,
    LONG_HFP,
    SHORT_HFP,
    HfpLayout,
)
from interpreter.hlasm.hfp_operation import HfpOperation, hfp_builtin_name
from interpreter.hlasm.hfp_slots import (
    DIVIDE_BIT,
    OVERFLOW_BIT,
    SIGNIFICANCE_BIT,
    SQUARE_ROOT_BIT,
    UNDERFLOW_BIT,
)
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult
from zarch_float.condition import Condition
from zarch_float.hfp_arithmetic import (
    hfp_add,
    hfp_compare,
    hfp_divide,
    hfp_halve,
    hfp_load_fp_integer,
    hfp_multiply,
    hfp_multiply_add,
    hfp_multiply_add_unnormalized,
    hfp_multiply_subtract,
    hfp_multiply_unnormalized,
    hfp_square_root,
    hfp_subtract,
)
from zarch_float.hfp_convert import hfp_to_bfp, hfp_to_integer
from zarch_float.hfp_result import HfpResult
from zarch_float.hfp_value import HfpValue
from zarch_float.integer_format import SIGNED_32, SIGNED_64, IntegerFormat
from zarch_float.rounding_mode import HFP_MODIFIER_MODES, HFP_TO_BFP_MODIFIER_MODES

type _Rule = Callable[[Sequence[HfpValue]], HfpResult]
type _Unary = Callable[[HfpValue], HfpResult]
type _Binary = Callable[[HfpValue, HfpValue], HfpResult]
type _Ternary = Callable[[HfpValue, HfpValue, HfpValue], HfpResult]

SPECIAL_CC = 3
POSITIVE_CC = 2


_BITS: Mapping[Condition, int] = {
    Condition.HFP_SIGNIFICANCE: SIGNIFICANCE_BIT,
    Condition.HFP_EXPONENT_UNDERFLOW: UNDERFLOW_BIT,
    Condition.HFP_EXPONENT_OVERFLOW: OVERFLOW_BIT,
    Condition.HFP_DIVIDE: DIVIDE_BIT,
    Condition.HFP_SQUARE_ROOT: SQUARE_ROOT_BIT,
}


def _operand(arg: TypedValue, layout: HfpLayout) -> HfpValue:
    negative, characteristic, fraction = arg.value
    return HfpValue(
        layout.format, bool(negative), int(fraction), int(characteristic) - EXCESS
    )


def _outcome(result: HfpResult) -> list[int]:
    value = result.value
    return [
        int(value.negative),
        (value.exponent + EXCESS) & CHARACTERISTIC_MASK,
        value.fraction,
        sum(bit for condition, bit in _BITS.items() if condition in result.conditions),
    ]


def _apply(rule: _Rule, layout: HfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        operands = tuple(_operand(arg, layout) for arg in args)
        return BuiltinResult(value=_outcome(rule(operands)))

    return call


def _compare(layout: HfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        a, b = (_operand(arg, layout) for arg in args)
        return BuiltinResult(value=hfp_compare(a, b).comparison.value)

    return call


def _source_cc(a: HfpValue, special: bool) -> int:
    return SPECIAL_CC if special else (a.fraction != 0) * (POSITIVE_CC - a.negative)


def _to_fixed(target: IntegerFormat, layout: HfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a = args
        operand = _operand(a, layout)
        result = hfp_to_integer(operand, target, HFP_MODIFIER_MODES[int(mode.value)])
        image = result.value & (target.maximum - target.minimum)
        special = Condition.OUT_OF_RANGE in result.conditions
        return BuiltinResult(value=[image, _source_cc(operand, special)])

    return call


def _to_bfp(target: BfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        mode, a = args
        operand = _operand(a, LONG_HFP)
        method = HFP_TO_BFP_MODIFIER_MODES[int(mode.value)]
        result = hfp_to_bfp(operand, target.format, method)
        special = Condition.OVERFLOW in result.conditions
        fields = fields_of(result.value).as_list()
        return BuiltinResult(value=[*fields, _source_cc(operand, special)])

    return call


def _unary(rule: _Unary) -> _Rule:
    return lambda operands: rule(operands[0])


def _binary(rule: _Binary) -> _Rule:
    return lambda operands: rule(operands[0], operands[1])


def _ternary(rule: _Ternary) -> _Rule:
    return lambda operands: rule(operands[0], operands[1], operands[2])


def _normalized(
    normalize: bool, rule: Callable[[HfpValue, HfpValue, bool], HfpResult]
) -> _Binary:
    return lambda a, b: rule(a, b, normalize)


def _into(target: HfpLayout) -> _Binary:
    return lambda a, b: hfp_multiply(a, b, target.format)


_ALL = (SHORT_HFP, LONG_HFP, EXTENDED_HFP)
_SHORT_AND_LONG = (SHORT_HFP, LONG_HFP)

_RULES: Mapping[HfpOperation, tuple[_Rule, tuple[HfpLayout, ...]]] = {
    HfpOperation.ADD: (_binary(_normalized(True, hfp_add)), _ALL),
    HfpOperation.SUBTRACT: (_binary(_normalized(True, hfp_subtract)), _ALL),
    HfpOperation.ADD_UNNORMALIZED: (
        _binary(_normalized(False, hfp_add)),
        _SHORT_AND_LONG,
    ),
    HfpOperation.SUBTRACT_UNNORMALIZED: (
        _binary(_normalized(False, hfp_subtract)),
        _SHORT_AND_LONG,
    ),
    HfpOperation.DIVIDE: (_binary(hfp_divide), _ALL),
    HfpOperation.MULTIPLY_UNNORMALIZED: (
        _binary(hfp_multiply_unnormalized),
        (LONG_HFP,),
    ),
    HfpOperation.HALVE: (_unary(hfp_halve), _SHORT_AND_LONG),
    HfpOperation.SQUARE_ROOT: (_unary(hfp_square_root), _ALL),
    HfpOperation.LOAD_FP_INTEGER: (_unary(hfp_load_fp_integer), _ALL),
    HfpOperation.MULTIPLY_ADD: (_ternary(hfp_multiply_add), _SHORT_AND_LONG),
    HfpOperation.MULTIPLY_SUBTRACT: (_ternary(hfp_multiply_subtract), _SHORT_AND_LONG),
    HfpOperation.MULTIPLY_ADD_UNNORMALIZED: (
        _ternary(hfp_multiply_add_unnormalized),
        (LONG_HFP,),
    ),
}
_MULTIPLIES = (
    (HfpOperation.MULTIPLY, SHORT_HFP, SHORT_HFP),
    (HfpOperation.MULTIPLY, LONG_HFP, LONG_HFP),
    (HfpOperation.MULTIPLY, EXTENDED_HFP, EXTENDED_HFP),
    (HfpOperation.MULTIPLY_LENGTHENED, SHORT_HFP, LONG_HFP),
    (HfpOperation.MULTIPLY_LENGTHENED, LONG_HFP, EXTENDED_HFP),
)


_TO_FIXED: Mapping[HfpOperation, IntegerFormat] = {
    HfpOperation.TO_FIXED_32: SIGNED_32,
    HfpOperation.TO_FIXED_64: SIGNED_64,
}
_TO_BFP: Mapping[HfpOperation, BfpLayout] = {
    HfpOperation.TO_BFP_SHORT: SHORT_BFP,
    HfpOperation.TO_BFP_LONG: LONG_BFP,
}


def hfp_builtins() -> Mapping[FuncName, Builtin]:
    return {
        **{
            hfp_builtin_name(op, layout): _to_fixed(target, layout)
            for op, target in _TO_FIXED.items()
            for layout in _ALL
        },
        **{
            hfp_builtin_name(op, LONG_HFP): _to_bfp(target)
            for op, target in _TO_BFP.items()
        },
        **{
            hfp_builtin_name(op, layout): _apply(rule, layout)
            for op, (rule, layouts) in _RULES.items()
            for layout in layouts
        },
        **{
            hfp_builtin_name(op, source): _apply(_binary(_into(target)), source)
            for op, source, target in _MULTIPLIES
        },
        **{
            hfp_builtin_name(HfpOperation.COMPARE, layout): _compare(layout)
            for layout in _ALL
        },
    }
