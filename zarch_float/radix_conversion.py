# pyright: standard
"""PFPO convert floating-point radix (PoO 9-35 to 9-46): a value of one radix rounded once into a format of another, with PFPO's scaled value (1 <= |z| < radix) and scaling exponent for a trapped overflow or underflow."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from fractions import Fraction

from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_rounding import BfpRounding
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition, raised
from zarch_float.dfp_context import quotient
from zarch_float.dfp_format import DfpFormat
from zarch_float.dfp_result import DfpResult
from zarch_float.dfp_rounding import DfpRounding
from zarch_float.dfp_value import DfpValue
from zarch_float.exact_rounding import leading_exponent, round_ratio
from zarch_float.float_kind import FloatKind
from zarch_float.hfp_format import HfpFormat
from zarch_float.hfp_value import HfpValue
from zarch_float.radix_controls import RadixControls
from zarch_float.radix_result import FloatValue, RadixResult, radix_exact
from zarch_float.radix_source import RadixSource
from zarch_float.rounding_mode import RoundingMode

type FloatFormat = BfpFormat | HfpFormat | DfpFormat
type _Kinds = Mapping[FloatKind, Callable[[], RadixResult]]

HFP_MIN_EXPONENT = -64
HFP_MAX_EXPONENT = 63
HEX = 16
DECIMAL = 10
NO_SCALING = 0
_TRAPPED = frozenset({Condition.OVERFLOW, Condition.TINY})


def radix_source(value: FloatValue) -> RadixSource:
    match value:
        case HfpValue():
            kind = FloatKind.FINITE if value.fraction else FloatKind.ZERO
            return RadixSource(value.negative, kind, value.magnitude(), 0)
        case BfpValue() | DfpValue():
            payload = value.significand if value.is_nan() else 0
            return RadixSource(value.negative, value.kind, value.magnitude(), payload)


def _signaled(source: RadixSource) -> frozenset[Condition]:
    return raised((Condition.INVALID, source.kind is FloatKind.SNAN))


def _signed(source: RadixSource) -> Fraction:
    return -source.magnitude if source.negative else source.magnitude


def _bfp_nan(source: RadixSource, target: BfpFormat) -> RadixResult:
    payload = source.payload if source.payload < 1 << (target.precision - 2) else 0
    value = BfpValue(target, source.negative, FloatKind.QNAN, payload)
    return radix_exact(value, _signaled(source))


def _bfp_finite(
    source: RadixSource, target: BfpFormat, mode: RoundingMode
) -> RadixResult:
    rounding = BfpRounding(target, mode, target, NO_SCALING)
    rounded = rounding.round(source.negative, source.magnitude)
    if not rounded.conditions & _TRAPPED:
        return radix_exact(rounded.value, rounded.conditions)
    precise = rounded.scaled
    unit = 1 - target.precision
    scaled = replace(precise, exponent=unit)
    return RadixResult(
        rounded.value,
        rounded.conditions,
        scaled,
        rounded.scaled_conditions,
        precise.exponent - unit,
    )


def _to_bfp(
    source: RadixSource, target: BfpFormat, mode: RoundingMode, controls: RadixControls
) -> RadixResult:
    kinds: _Kinds = {
        FloatKind.ZERO: lambda: radix_exact(
            BfpValue(target, source.negative, FloatKind.ZERO)
        ),
        FloatKind.INFINITY: lambda: radix_exact(
            BfpValue(target, source.negative, FloatKind.INFINITY)
        ),
        FloatKind.QNAN: lambda: _bfp_nan(source, target),
        FloatKind.SNAN: lambda: _bfp_nan(source, target),
        FloatKind.FINITE: lambda: _bfp_finite(source, target, mode),
    }
    return kinds[source.kind]()


def _dfp_nan(source: RadixSource, target: DfpFormat) -> RadixResult:
    payload = (
        source.payload if source.payload < DECIMAL ** (target.precision - 1) else 0
    )
    value = DfpValue(target, source.negative, FloatKind.QNAN, payload)
    return radix_exact(value, _signaled(source))


def _trailing_zeros(significand: int) -> int:
    digits = str(significand)
    return len(digits) - len(digits.rstrip("0"))


def _largest_quantum(value: DfpValue) -> DfpValue:
    room = value.format.quantum_max - value.exponent
    shift = min(_trailing_zeros(value.significand), room)
    return replace(
        value,
        significand=value.significand // DECIMAL**shift,
        exponent=value.exponent + shift,
    )


def _dfp_delivered(result: DfpResult, controls: RadixControls) -> RadixResult:
    value, conditions = result.value, result.conditions
    if Condition.INEXACT in conditions:
        return radix_exact(value, conditions | {Condition.QUANTUM})
    if not controls.quantum_of_one:
        return radix_exact(_largest_quantum(value), conditions)
    off_one = raised((Condition.QUANTUM, value.exponent > 0))
    return radix_exact(value, conditions | off_one)


def _dfp_scaled(rounded_scaled: DfpValue) -> tuple[DfpValue, int]:
    precision = rounded_scaled.format.precision
    digits = len(str(rounded_scaled.significand))
    scaled = replace(
        rounded_scaled,
        significand=rounded_scaled.significand * DECIMAL ** (precision - digits),
        exponent=1 - precision,
    )
    return scaled, rounded_scaled.exponent + digits - 1


def _dfp_finite(
    source: RadixSource, target: DfpFormat, mode: RoundingMode, controls: RadixControls
) -> RadixResult:
    signed = _signed(source)
    divided = quotient(signed.numerator, signed.denominator)
    rounding = DfpRounding(target, mode, target, NO_SCALING)
    rounded = rounding.apply(divided, lambda: signed)
    delivered = _dfp_delivered(rounded, controls)
    if not rounded.conditions & _TRAPPED:
        return delivered
    scaled, scaling = _dfp_scaled(rounded.scaled)
    return replace(
        delivered,
        scaled=scaled,
        scaled_conditions=rounded.scaled_conditions,
        scaling=scaling,
    )


def _to_dfp(
    source: RadixSource, target: DfpFormat, mode: RoundingMode, controls: RadixControls
) -> RadixResult:
    zero_exponent = 0 if controls.quantum_of_one else target.quantum_max
    kinds: _Kinds = {
        FloatKind.ZERO: lambda: radix_exact(
            DfpValue(target, source.negative, FloatKind.ZERO, 0, zero_exponent)
        ),
        FloatKind.INFINITY: lambda: radix_exact(
            DfpValue(target, source.negative, FloatKind.INFINITY)
        ),
        FloatKind.QNAN: lambda: _dfp_nan(source, target),
        FloatKind.SNAN: lambda: _dfp_nan(source, target),
        FloatKind.FINITE: lambda: _dfp_finite(source, target, mode, controls),
    }
    return kinds[source.kind]()


def _hmax(target: HfpFormat, negative: bool) -> HfpValue:
    return HfpValue(target, negative, HEX**target.digits - 1, HFP_MAX_EXPONENT)


def _true_zero(target: HfpFormat, negative: bool) -> HfpValue:
    return HfpValue(target, negative, 0, HFP_MIN_EXPONENT)


def _hfp_invalid(value: HfpValue) -> RadixResult:
    return radix_exact(value, frozenset({Condition.INVALID}))


def _hfp_out_of_range(
    value: HfpValue,
    reported: frozenset[Condition],
    precise: tuple[HfpValue, frozenset[Condition]],
) -> RadixResult:
    rounded, flags = precise
    scaled = replace(rounded, exponent=1)
    return RadixResult(value, reported, scaled, flags, rounded.exponent - 1)


def _hfp_overflow(
    precise: tuple[HfpValue, frozenset[Condition]], controls: RadixControls
) -> RadixResult:
    rounded = precise[0]
    largest = _hmax(rounded.format, rounded.negative)
    if not controls.hfp_overflow:
        return _hfp_invalid(largest)
    reported = frozenset({Condition.OVERFLOW, Condition.INEXACT})
    return _hfp_out_of_range(largest, reported, precise)


def _hfp_underflow(
    precise: tuple[HfpValue, frozenset[Condition]], controls: RadixControls
) -> RadixResult:
    rounded = precise[0]
    zero = _true_zero(rounded.format, rounded.negative)
    if not controls.hfp_underflow:
        return radix_exact(zero, frozenset({Condition.INEXACT}))
    reported = frozenset({Condition.TINY, Condition.UNDERFLOW, Condition.INEXACT})
    return _hfp_out_of_range(zero, reported, precise)


def _hfp_rounded(
    source: RadixSource, target: HfpFormat, mode: RoundingMode
) -> tuple[HfpValue, frozenset[Condition]]:
    exponent = leading_exponent(source.magnitude) // 4 + 1
    scaled = source.magnitude * Fraction(HEX) ** (target.digits - exponent)
    rounded = round_ratio(scaled.numerator, scaled.denominator, mode, source.negative)
    carried = rounded.magnitude >> 4 * target.digits
    fraction = rounded.magnitude >> 4 * carried
    flags = raised(
        (Condition.INEXACT, rounded.inexact),
        (Condition.INCREMENTED, rounded.incremented),
    )
    value = HfpValue(target, source.negative, fraction, exponent + carried)
    return value, flags


def _hfp_finite(
    source: RadixSource, target: HfpFormat, mode: RoundingMode, controls: RadixControls
) -> RadixResult:
    precise = _hfp_rounded(source, target, mode)
    value, flags = precise
    if value.exponent > HFP_MAX_EXPONENT:
        return _hfp_overflow(precise, controls)
    if value.exponent < HFP_MIN_EXPONENT:
        return _hfp_underflow(precise, controls)
    return radix_exact(value, flags)


def _to_hfp(
    source: RadixSource, target: HfpFormat, mode: RoundingMode, controls: RadixControls
) -> RadixResult:
    kinds: _Kinds = {
        FloatKind.ZERO: lambda: radix_exact(_true_zero(target, source.negative)),
        FloatKind.INFINITY: lambda: _hfp_invalid(_hmax(target, source.negative)),
        FloatKind.QNAN: lambda: _hfp_invalid(_hmax(target, False)),
        FloatKind.SNAN: lambda: _hfp_invalid(_hmax(target, False)),
        FloatKind.FINITE: lambda: _hfp_finite(source, target, mode, controls),
    }
    return kinds[source.kind]()


def _to_ieee(
    source: RadixSource,
    target: BfpFormat | DfpFormat,
    mode: RoundingMode,
    controls: RadixControls,
) -> RadixResult:
    match target:
        case BfpFormat():
            return _to_bfp(source, target, mode, controls)
        case DfpFormat():
            return _to_dfp(source, target, mode, controls)


def convert_radix(
    value: FloatValue, target: FloatFormat, mode: RoundingMode, controls: RadixControls
) -> RadixResult:
    source = radix_source(value)
    if isinstance(target, HfpFormat):
        return _to_hfp(source, target, mode, controls)
    return _to_ieee(source, target, mode, controls)
