# pyright: standard
"""The PFPO radix-conversion builtin over zarch_float; the "too cumbersome" clause: converting an exact value of one radix into another with eight rounding methods would dwarf the program. GR0's function word carries the formats and controls, so the builtin takes it, the rounding modifier and the source fields."""

from collections.abc import Mapping, Sequence

from interpreter.func_name import FuncName
from interpreter.hlasm.bfp_fields import BfpFields, fields_of, value_of
from interpreter.hlasm.bfp_layout import BfpLayout
from interpreter.hlasm.dfp_fields import dfp_fields_of, dfp_value_of
from interpreter.hlasm.dfp_layout import DfpLayout
from interpreter.hlasm.hfp_layout import (
    CHARACTERISTIC_MASK,
    EXCESS,
    HfpLayout,
)
from interpreter.hlasm.ieee_words import ieee_words
from interpreter.hlasm.pfpo_formats import LAYOUTS, PFPO_BUILTIN, PfpoLayout
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.dfp_value import DfpValue
from zarch_float.hfp_value import HfpValue
from zarch_float.radix_controls import RadixControls
from zarch_float.radix_conversion import convert_radix
from zarch_float.radix_result import FloatValue
from zarch_float.rounding_mode import DFP_MODIFIER_MODES

WORD_MASK = 0xFFFFFFFF
TARGET_SHIFT = 16
SOURCE_SHIFT = 8
CODE_MASK = 0xFF
INEXACT_SUPPRESSION = 0x80
FIRST_CONTROL = 0x20
SECOND_CONTROL = 0x10


def _ieee_value(layout: BfpLayout | DfpLayout, fields: Sequence[int]) -> FloatValue:
    negative, exponent, significand = fields
    match layout:
        case BfpLayout():
            return value_of(
                BfpFields(bool(negative), exponent, significand), layout.format
            )
        case DfpLayout():
            return dfp_value_of(fields, layout.format)


def _value(layout: PfpoLayout, fields: Sequence[int]) -> FloatValue:
    negative, exponent, significand = fields
    if isinstance(layout, HfpLayout):
        return HfpValue(layout.format, bool(negative), significand, exponent - EXCESS)
    return _ieee_value(layout, fields)


def _ieee_fields(value: BfpValue | DfpValue) -> list[int]:
    match value:
        case BfpValue():
            return fields_of(value).as_list()
        case DfpValue():
            return dfp_fields_of(value)


def _fields(value: FloatValue) -> list[int]:
    if isinstance(value, HfpValue):
        characteristic = (value.exponent + EXCESS) & CHARACTERISTIC_MASK
        return [int(value.negative), characteristic, value.fraction]
    return _ieee_fields(value)


def _suppressed(word: int) -> frozenset[Condition]:
    return frozenset(
        condition
        for condition, kept in (
            (Condition.INEXACT, not word & INEXACT_SUPPRESSION),
            (Condition.QUANTUM, bool(word & FIRST_CONTROL)),
        )
        if not kept
    )


def _pfpo(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
    word, mode, fields = args
    function = int(word.value)
    target = LAYOUTS[(function >> TARGET_SHIFT) & CODE_MASK]
    source = LAYOUTS[(function >> SOURCE_SHIFT) & CODE_MASK]
    controls = RadixControls(
        bool(function & FIRST_CONTROL),
        bool(function & SECOND_CONTROL),
        bool(function & SECOND_CONTROL),
    )
    operand = _value(source, [int(field) for field in fields.value])
    result = convert_radix(
        operand, target.format, DFP_MODIFIER_MODES[int(mode.value)], controls
    )
    conditions = result.conditions - _suppressed(function)
    return BuiltinResult(
        value=[
            *_fields(result.value),
            *_fields(result.scaled),
            *ieee_words(conditions, result.scaled_conditions),
            result.scaling & WORD_MASK,
        ]
    )


def pfpo_builtins() -> Mapping[FuncName, Builtin]:
    return {PFPO_BUILTIN: _pfpo}
