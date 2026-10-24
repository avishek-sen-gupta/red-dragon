# pyright: standard
"""Images of E, D and L DC nominals, rounded and packed at assembly time: HFP without a type extension or with H or Q, BFP with B and DFP with D (HLASM Language Reference SC26-4940-09, pp. 148-158), with the warnings a type-extended conversion raises."""

from collections.abc import Callable, Mapping
from fractions import Fraction

from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.origin import Origin
from interpreter.hlasm.dc_characteristic_out_of_range import DcCharacteristicOutOfRange
from interpreter.hlasm.dc_exponent_out_of_range import (
    NOMINAL_EXPONENT_RANGE,
    DcExponentOutOfRange,
)
from interpreter.hlasm.dc_length_wrong import DcLengthWrong
from interpreter.hlasm.dc_precision_lost import DcPrecisionLost
from interpreter.hlasm.dc_warning import DcWarning
from interpreter.hlasm.encoded_value import EncodedValue
from interpreter.hlasm.float_nominal import FloatNominal, parse_float_nominal
from interpreter.hlasm.float_number import FloatNumber
from interpreter.hlasm.float_special import FloatSpecial
from interpreter.hlasm.float_special_value import FloatSpecialValue
from interpreter.project.dc_warning_kind import DcWarningKind
from zarch_float import bfp_format, dfp_format
from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_image import bfp_image
from zarch_float.bfp_rounding import rounding_into
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.dfp_convert import dfp_fitted
from zarch_float.dfp_format import DfpFormat
from zarch_float.dfp_image import dfp_image
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind
from zarch_float.hfp_image import hfp_image
from zarch_float.hfp_rounding import hfp_rounded, hfp_rounded_at
from zarch_float.hfp_value import HfpValue
from zarch_float.rounding_mode import (
    BFP_MODIFIER_MODES,
    DFP_MODIFIER_MODES,
    HFP_MODIFIER_MODES,
    RoundingMode,
)

type FloatEncoder = Callable[[DcItem, str, FloatNominal, int, Origin], EncodedValue]

_HEX_BASE = Fraction(16)
_HFP_EXPONENTS = range(-64, 64)
_HFP_MAX_EXPONENT = 63
_HFP_MIN_EXPONENT = -64
_HFP_SIGN_AND_CHARACTERISTIC_BITS = 8
_HFP_HALF_BITS = 64
_HFP_LOW_FRACTION_START = 72
_BFP_SIGN_BITS = 1
_BFP_NAN_FRACTION_BITS = 2
_INFINITY_AND_NANS = frozenset(
    {
        FloatSpecialValue.INF,
        FloatSpecialValue.NAN,
        FloatSpecialValue.QNAN,
        FloatSpecialValue.SNAN,
    }
)
_WARNED_CONDITIONS = (
    (Condition.OVERFLOW, DcWarningKind.OVERFLOW),
    (Condition.UNDERFLOW, DcWarningKind.UNDERFLOW),
    (Condition.INEXACT, DcWarningKind.INEXACT),
)

_BFP_FORMATS: Mapping[str, BfpFormat] = {
    "E": bfp_format.SHORT,
    "D": bfp_format.LONG,
    "L": bfp_format.EXTENDED,
}
_DFP_FORMATS: Mapping[str, DfpFormat] = {
    "E": dfp_format.SHORT,
    "D": dfp_format.LONG,
    "L": dfp_format.EXTENDED,
}


def _constant(item: DcItem, text: str) -> str:
    return f"{item.type}{item.extension}'{text}'"


def _warned(
    item: DcItem, text: str, conditions: frozenset[Condition]
) -> tuple[DcWarning, ...]:
    kinds = (kind for condition, kind in _WARNED_CONDITIONS if condition in conditions)
    return tuple(DcWarning(_constant(item, text), kind) for kind in kinds)[:1]


def _hfp_fraction_bits(bits: int) -> int:
    in_high_half = min(bits, _HFP_HALF_BITS) - _HFP_SIGN_AND_CHARACTERISTIC_BITS
    return in_high_half + max(bits - _HFP_LOW_FRACTION_START, 0)


def _hfp_value(
    item: DcItem, text: str, number: FloatNumber, bits: int, origin: Origin
) -> HfpValue:
    fraction_bits = _hfp_fraction_bits(bits)
    if fraction_bits <= 0:
        raise DcPrecisionLost(_constant(item, text), origin)
    mode = HFP_MODIFIER_MODES[number.rounding]
    magnitude = number.magnitude()
    value = hfp_rounded(fraction_bits, number.negative, magnitude, item.scale, mode)
    if value.fraction == 0:
        raise DcPrecisionLost(_constant(item, text), origin)
    return value


def _check_nominal_exponent(
    item: DcItem, text: str, number: FloatNumber, origin: Origin
) -> None:
    if number.written_exponent not in NOMINAL_EXPONENT_RANGE:
        raise DcExponentOutOfRange(_constant(item, text), origin)


def _unextended_number(
    item: DcItem, text: str, number: FloatNumber, bits: int, origin: Origin
) -> EncodedValue:
    _check_nominal_exponent(item, text, number, origin)
    if number.coefficient == 0:
        return EncodedValue(0)
    value = _hfp_value(item, text, number, bits, origin)
    if value.exponent not in _HFP_EXPONENTS:
        raise DcCharacteristicOutOfRange(_constant(item, text), origin)
    return EncodedValue(hfp_image(value, bits))


def _hfp_special_magnitudes(
    fraction_bits: int,
) -> Mapping[FloatSpecialValue, tuple[Fraction, int]]:
    unit = Fraction(1, 2**fraction_bits)
    return {
        FloatSpecialValue.MAX: (
            (1 - unit) * _HEX_BASE**_HFP_MAX_EXPONENT,
            _HFP_MAX_EXPONENT,
        ),
        FloatSpecialValue.MIN: (
            _HEX_BASE ** (_HFP_MIN_EXPONENT - 1),
            _HFP_MIN_EXPONENT,
        ),
        FloatSpecialValue.DMIN: (
            unit * _HEX_BASE**_HFP_MIN_EXPONENT,
            _HFP_MIN_EXPONENT,
        ),
    }


def _hfp_special(special: FloatSpecial, bits: int) -> EncodedValue:
    fraction_bits = _hfp_fraction_bits(bits)
    magnitude, exponent = _hfp_special_magnitudes(fraction_bits)[special.value]
    value = hfp_rounded_at(
        fraction_bits, special.negative, magnitude, exponent, RoundingMode.TOWARD_ZERO
    )
    return EncodedValue(hfp_image(value, bits))


def _hfp_in_range(
    value: HfpValue, fraction_bits: int, magnitude: Fraction, mode: RoundingMode
) -> tuple[HfpValue, Condition]:
    if value.exponent > _HFP_MAX_EXPONENT:
        largest, exponent = _hfp_special_magnitudes(fraction_bits)[
            FloatSpecialValue.MAX
        ]
        saturated = hfp_rounded_at(
            fraction_bits, value.negative, largest, exponent, mode
        )
        return saturated, Condition.OVERFLOW
    if value.exponent < _HFP_MIN_EXPONENT:
        denormalized = hfp_rounded_at(
            fraction_bits, value.negative, magnitude, _HFP_MIN_EXPONENT, mode
        )
        return denormalized, Condition.UNDERFLOW
    return value, Condition.INEXACT


def _hfp_conditions(
    value: HfpValue, magnitude: Fraction, condition: Condition
) -> frozenset[Condition]:
    if value.magnitude() == magnitude:
        return frozenset()
    return frozenset({condition, Condition.INEXACT})


def _extended_number(
    item: DcItem, text: str, number: FloatNumber, bits: int, origin: Origin
) -> EncodedValue:
    if number.coefficient == 0:
        return EncodedValue(int(number.negative) << (bits - 1))
    mode = HFP_MODIFIER_MODES[number.rounding]
    magnitude = number.magnitude()
    rounded = _hfp_value(item, text, number, bits, origin)
    value, condition = _hfp_in_range(rounded, _hfp_fraction_bits(bits), magnitude, mode)
    conditions = _hfp_conditions(value, magnitude, condition)
    return EncodedValue(hfp_image(value, bits), _warned(item, text, conditions))


def _unextended_hfp(
    item: DcItem, text: str, nominal: FloatNominal, bits: int, origin: Origin
) -> EncodedValue:
    match nominal:
        case FloatNumber():
            return _unextended_number(item, text, nominal, bits, origin)
        case FloatSpecial():
            return _hfp_special(nominal, bits)


def _extended_hfp(
    item: DcItem, text: str, nominal: FloatNominal, bits: int, origin: Origin
) -> EncodedValue:
    match nominal:
        case FloatNumber():
            return _extended_number(item, text, nominal, bits, origin)
        case FloatSpecial():
            return _hfp_special(nominal, bits)


def _bfp_exponent_bits(item: DcItem) -> int:
    return (2 * _BFP_FORMATS[item.type].emax + 1).bit_length()


def _bfp_format(item: DcItem, bits: int) -> BfpFormat:
    base = _BFP_FORMATS[item.type]
    return BfpFormat(bits - _bfp_exponent_bits(item), base.emax, base.trap_scale)


def _nan_payload(fmt: BfpFormat) -> int:
    return 1 << (fmt.precision - 1 - _BFP_NAN_FRACTION_BITS)


_BFP_SPECIALS: Mapping[FloatSpecialValue, Callable[[BfpFormat, bool], BfpValue]] = {
    FloatSpecialValue.INF: lambda fmt, negative: BfpValue(
        fmt, negative, FloatKind.INFINITY
    ),
    FloatSpecialValue.NAN: lambda fmt, negative: BfpValue(
        fmt, negative, FloatKind.QNAN
    ),
    FloatSpecialValue.QNAN: lambda fmt, negative: BfpValue(
        fmt, negative, FloatKind.QNAN, _nan_payload(fmt)
    ),
    FloatSpecialValue.SNAN: lambda fmt, negative: BfpValue(
        fmt, negative, FloatKind.SNAN, _nan_payload(fmt)
    ),
    FloatSpecialValue.MAX: lambda fmt, negative: BfpValue(
        fmt, negative, FloatKind.FINITE, 2**fmt.precision - 1, fmt.quantum_max
    ),
    FloatSpecialValue.MIN: lambda fmt, negative: BfpValue(
        fmt, negative, FloatKind.FINITE, 2 ** (fmt.precision - 1), fmt.quantum_min
    ),
    FloatSpecialValue.DMIN: lambda fmt, negative: BfpValue(
        fmt, negative, FloatKind.FINITE, 1, fmt.quantum_min
    ),
}


def _bfp_special(
    item: DcItem, text: str, special: FloatSpecial, bits: int, origin: Origin
) -> EncodedValue:
    shortest = _BFP_SIGN_BITS + _bfp_exponent_bits(item) + _BFP_NAN_FRACTION_BITS
    if special.value in _INFINITY_AND_NANS and bits < shortest:
        raise DcLengthWrong(_constant(item, text), shortest, origin)
    value = _BFP_SPECIALS[special.value](_bfp_format(item, bits), special.negative)
    return EncodedValue(bfp_image(value))


def _bfp_number(
    item: DcItem, text: str, number: FloatNumber, bits: int
) -> EncodedValue:
    fmt = _bfp_format(item, bits)
    if number.coefficient == 0:
        return EncodedValue(bfp_image(BfpValue(fmt, number.negative, FloatKind.ZERO)))
    mode = BFP_MODIFIER_MODES[number.rounding]
    result = rounding_into(fmt, mode).round(number.negative, number.magnitude())
    return EncodedValue(bfp_image(result.value), _warned(item, text, result.conditions))


def _bfp(
    item: DcItem, text: str, nominal: FloatNominal, bits: int, origin: Origin
) -> EncodedValue:
    match nominal:
        case FloatNumber():
            return _bfp_number(item, text, nominal, bits)
        case FloatSpecial():
            return _bfp_special(item, text, nominal, bits, origin)


_DFP_SPECIALS: Mapping[FloatSpecialValue, Callable[[DfpFormat, bool], DfpValue]] = {
    FloatSpecialValue.INF: lambda fmt, negative: DfpValue(
        fmt, negative, FloatKind.INFINITY
    ),
    FloatSpecialValue.NAN: lambda fmt, negative: DfpValue(
        fmt, negative, FloatKind.QNAN
    ),
    FloatSpecialValue.QNAN: lambda fmt, negative: DfpValue(
        fmt, negative, FloatKind.QNAN
    ),
    FloatSpecialValue.SNAN: lambda fmt, negative: DfpValue(
        fmt, negative, FloatKind.SNAN
    ),
    FloatSpecialValue.MAX: lambda fmt, negative: DfpValue(
        fmt, negative, FloatKind.FINITE, 10**fmt.precision - 1, fmt.quantum_max
    ),
    FloatSpecialValue.MIN: lambda fmt, negative: DfpValue(
        fmt, negative, FloatKind.FINITE, 1, fmt.emin
    ),
    FloatSpecialValue.DMIN: lambda fmt, negative: DfpValue(
        fmt, negative, FloatKind.FINITE, 1, fmt.quantum_min
    ),
}


def _dfp_number(item: DcItem, text: str, number: FloatNumber) -> EncodedValue:
    kind = FloatKind.FINITE if number.coefficient else FloatKind.ZERO
    written = DfpValue(
        _DFP_FORMATS[item.type],
        number.negative,
        kind,
        number.coefficient,
        number.exponent,
    )
    result = dfp_fitted(written, DFP_MODIFIER_MODES[number.rounding])
    return EncodedValue(dfp_image(result.value), _warned(item, text, result.conditions))


def _dfp(
    item: DcItem, text: str, nominal: FloatNominal, bits: int, origin: Origin
) -> EncodedValue:
    match nominal:
        case FloatNumber():
            return _dfp_number(item, text, nominal)
        case FloatSpecial():
            fmt = _DFP_FORMATS[item.type]
            return EncodedValue(
                dfp_image(_DFP_SPECIALS[nominal.value](fmt, nominal.negative))
            )


_FAMILIES: Mapping[str, FloatEncoder] = {
    "": _unextended_hfp,
    "H": _extended_hfp,
    "Q": _extended_hfp,
    "B": _bfp,
    "D": _dfp,
}


def floating_point_image(
    item: DcItem, text: str, bits: int, origin: Origin
) -> EncodedValue:
    nominal = parse_float_nominal(item, text)
    return _FAMILIES[item.extension](item, text, nominal, bits, origin)
