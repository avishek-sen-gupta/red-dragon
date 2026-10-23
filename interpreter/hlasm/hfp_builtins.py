# pyright: standard
"""The HFP arithmetic builtins over zarch_float; the "too cumbersome" clause: guard-digit alignment, normalization and exact products, quotients and roots of up to 28 hexadecimal digits in IR would dwarf the program."""

from collections.abc import Callable, Mapping, Sequence

from interpreter.func_name import FuncName
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
from zarch_float.hfp_result import HfpResult
from zarch_float.hfp_value import HfpValue

type _Rule = Callable[..., HfpResult]
type _Binary = Callable[[HfpValue, HfpValue], HfpResult]


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
        operands = (_operand(arg, layout) for arg in args)
        return BuiltinResult(value=_outcome(rule(*operands)))

    return call


def _compare(layout: HfpLayout) -> Builtin:
    def call(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        a, b = (_operand(arg, layout) for arg in args)
        return BuiltinResult(value=hfp_compare(a, b).comparison.value)

    return call


def _normalized(
    normalize: bool, rule: Callable[[HfpValue, HfpValue, bool], HfpResult]
) -> _Binary:
    return lambda a, b: rule(a, b, normalize)


def _into(target: HfpLayout) -> _Binary:
    return lambda a, b: hfp_multiply(a, b, target.format)


_ALL = (SHORT_HFP, LONG_HFP, EXTENDED_HFP)
_SHORT_AND_LONG = (SHORT_HFP, LONG_HFP)

_RULES: Mapping[HfpOperation, tuple[_Rule, tuple[HfpLayout, ...]]] = {
    HfpOperation.ADD: (_normalized(True, hfp_add), _ALL),
    HfpOperation.SUBTRACT: (_normalized(True, hfp_subtract), _ALL),
    HfpOperation.ADD_UNNORMALIZED: (_normalized(False, hfp_add), _SHORT_AND_LONG),
    HfpOperation.SUBTRACT_UNNORMALIZED: (
        _normalized(False, hfp_subtract),
        _SHORT_AND_LONG,
    ),
    HfpOperation.DIVIDE: (hfp_divide, _ALL),
    HfpOperation.MULTIPLY_UNNORMALIZED: (hfp_multiply_unnormalized, (LONG_HFP,)),
    HfpOperation.HALVE: (hfp_halve, _SHORT_AND_LONG),
    HfpOperation.SQUARE_ROOT: (hfp_square_root, _ALL),
    HfpOperation.LOAD_FP_INTEGER: (hfp_load_fp_integer, _ALL),
    HfpOperation.MULTIPLY_ADD: (hfp_multiply_add, _SHORT_AND_LONG),
    HfpOperation.MULTIPLY_SUBTRACT: (hfp_multiply_subtract, _SHORT_AND_LONG),
    HfpOperation.MULTIPLY_ADD_UNNORMALIZED: (
        hfp_multiply_add_unnormalized,
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


def hfp_builtins() -> Mapping[FuncName, Builtin]:
    return {
        **{
            hfp_builtin_name(op, layout): _apply(rule, layout)
            for op, (rule, layouts) in _RULES.items()
            for layout in layouts
        },
        **{
            hfp_builtin_name(op, source): _apply(_into(target), source)
            for op, source, target in _MULTIPLIES
        },
        **{
            hfp_builtin_name(HfpOperation.COMPARE, layout): _compare(layout)
            for layout in _ALL
        },
    }
