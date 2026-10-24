# pyright: standard
"""Images of E, D and L DC nominals, rounded and packed at assembly time: HFP without a type extension or with H or Q, BFP with B and DFP with D (HLASM Language Reference SC26-4940-09, pp. 148-158)."""

from collections.abc import Callable, Mapping
from fractions import Fraction

from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.origin import Origin
from interpreter.hlasm.dc_characteristic_out_of_range import DcCharacteristicOutOfRange
from interpreter.hlasm.dc_exponent_out_of_range import (
    NOMINAL_EXPONENT_RANGE,
    DcExponentOutOfRange,
)
from interpreter.hlasm.dc_precision_lost import DcPrecisionLost
from interpreter.hlasm.hlasm_lowering_error import HlasmLoweringError
from zarch_float import bfp_format, dfp_format
from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_image import bfp_image
from zarch_float.bfp_rounding import rounding_into
from zarch_float.bfp_value import BfpValue
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

type FloatEncoder = Callable[[DcItem, str, int, Origin], int]

_SPACE = " "
_MINUS = "-"
_SIGNS = "+-"
_SPECIAL_OPEN = "("
_SPECIAL_CLOSE = ")"
_ROUNDING = "R"
_EXPONENT = "E"
_DECIMAL_POINT = "."
_DECIMAL_BASE = Fraction(10)
_HEX_BASE = Fraction(16)
_HFP_DEFAULT_ROUNDING = "1"
_BFP_DEFAULT_ROUNDING = "4"
_DFP_DEFAULT_ROUNDING = "8"
_HFP_EXPONENTS = range(-64, 64)
_HFP_MAX_EXPONENT = 63
_HFP_MIN_EXPONENT = -64
_HFP_SIGN_AND_CHARACTERISTIC_BITS = 8
_HFP_HALF_BITS = 64
_HFP_LOW_FRACTION_START = 72
_BFP_NAN_FRACTION_BITS = 2
_BFP_SIGN_BITS = 1
_EXPONENT_PAST_EVERY_FORMAT = 20_000
_INFINITY_AND_NANS = frozenset({"INF", "NAN", "QNAN", "SNAN"})

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


def _cleaned(text: str) -> str:
    return text.replace(_SPACE, "").upper()


def _negative(text: str) -> bool:
    return _cleaned(text).startswith(_MINUS)


def _body(text: str) -> str:
    return _cleaned(text).lstrip(_SIGNS)


def _is_special(text: str) -> bool:
    return _body(text).startswith(_SPECIAL_OPEN)


def _special_name(text: str) -> str:
    return _body(text).strip(_SPECIAL_OPEN + _SPECIAL_CLOSE)


def _number(text: str) -> str:
    return _body(text).partition(_ROUNDING)[0]


def _rounding_code(text: str, default: str) -> str:
    return _body(text).partition(_ROUNDING)[2] or default


def _mantissa(text: str) -> str:
    return _number(text).partition(_EXPONENT)[0]


def _written_exponent(item: DcItem, text: str) -> int:
    return int(_number(text).partition(_EXPONENT)[2] or "0") + item.exponent


def _exponent(item: DcItem, text: str) -> int:
    return max(
        -_EXPONENT_PAST_EVERY_FORMAT,
        min(_EXPONENT_PAST_EVERY_FORMAT, _written_exponent(item, text)),
    )


def _magnitude(item: DcItem, text: str) -> Fraction:
    return Fraction(_mantissa(text)) * _DECIMAL_BASE ** _exponent(item, text)


def _constant(item: DcItem, text: str) -> str:
    return f"{item.type}{item.extension}'{text}'"


def _hfp_fraction_bits(bits: int) -> int:
    in_high_half = min(bits, _HFP_HALF_BITS) - _HFP_SIGN_AND_CHARACTERISTIC_BITS
    return in_high_half + max(bits - _HFP_LOW_FRACTION_START, 0)


def _hfp_value(
    item: DcItem, text: str, bits: int, origin: Origin, mode: RoundingMode
) -> HfpValue:
    fraction_bits = _hfp_fraction_bits(bits)
    if fraction_bits <= 0:
        raise DcPrecisionLost(_constant(item, text), origin)
    magnitude = _magnitude(item, text)
    value = hfp_rounded(fraction_bits, _negative(text), magnitude, item.scale, mode)
    if value.fraction == 0:
        raise DcPrecisionLost(_constant(item, text), origin)
    return value


def _check_nominal_exponent(item: DcItem, text: str, origin: Origin) -> None:
    if _written_exponent(item, text) not in NOMINAL_EXPONENT_RANGE:
        raise DcExponentOutOfRange(_constant(item, text), origin)


def _unextended_hfp(item: DcItem, text: str, bits: int, origin: Origin) -> int:
    _check_nominal_exponent(item, text, origin)
    if _magnitude(item, text) == 0:
        return 0
    value = _hfp_value(item, text, bits, origin, RoundingMode.NEAREST_AWAY)
    if value.exponent not in _HFP_EXPONENTS:
        raise DcCharacteristicOutOfRange(_constant(item, text), origin)
    return hfp_image(value, bits)


def _hfp_special_magnitudes(fraction_bits: int) -> Mapping[str, tuple[Fraction, int]]:
    unit = Fraction(1, 2**fraction_bits)
    return {
        "MAX": ((1 - unit) * _HEX_BASE**_HFP_MAX_EXPONENT, _HFP_MAX_EXPONENT),
        "MIN": (_HEX_BASE ** (_HFP_MIN_EXPONENT - 1), _HFP_MIN_EXPONENT),
        "DMIN": (unit * _HEX_BASE**_HFP_MIN_EXPONENT, _HFP_MIN_EXPONENT),
    }


def _hfp_special(text: str, bits: int) -> int:
    fraction_bits = _hfp_fraction_bits(bits)
    magnitude, exponent = _hfp_special_magnitudes(fraction_bits)[_special_name(text)]
    value = hfp_rounded_at(
        fraction_bits, _negative(text), magnitude, exponent, RoundingMode.TOWARD_ZERO
    )
    return hfp_image(value, bits)


def _hfp_in_range(
    value: HfpValue, fraction_bits: int, magnitude: Fraction, mode: RoundingMode
) -> HfpValue:
    if value.exponent > _HFP_MAX_EXPONENT:
        largest, exponent = _hfp_special_magnitudes(fraction_bits)["MAX"]
        return hfp_rounded_at(fraction_bits, value.negative, largest, exponent, mode)
    if value.exponent < _HFP_MIN_EXPONENT:
        return hfp_rounded_at(
            fraction_bits, value.negative, magnitude, _HFP_MIN_EXPONENT, mode
        )
    return value


def _extended_hfp(item: DcItem, text: str, bits: int, origin: Origin) -> int:
    if _is_special(text):
        return _hfp_special(text, bits)
    if _magnitude(item, text) == 0:
        return int(_negative(text)) << (bits - 1)
    mode = HFP_MODIFIER_MODES[int(_rounding_code(text, _HFP_DEFAULT_ROUNDING))]
    value = _hfp_value(item, text, bits, origin, mode)
    fraction_bits = _hfp_fraction_bits(bits)
    return hfp_image(
        _hfp_in_range(value, fraction_bits, _magnitude(item, text), mode), bits
    )


def _bfp_exponent_bits(item: DcItem) -> int:
    return (2 * _BFP_FORMATS[item.type].emax + 1).bit_length()


def _bfp_format(item: DcItem, bits: int) -> BfpFormat:
    base = _BFP_FORMATS[item.type]
    return BfpFormat(bits - _bfp_exponent_bits(item), base.emax, base.trap_scale)


def _bfp_specials(fmt: BfpFormat, negative: bool) -> Mapping[str, BfpValue]:
    payload = 1 << (fmt.precision - 1 - _BFP_NAN_FRACTION_BITS)
    return {
        "INF": BfpValue(fmt, negative, FloatKind.INFINITY),
        "NAN": BfpValue(fmt, negative, FloatKind.QNAN),
        "QNAN": BfpValue(fmt, negative, FloatKind.QNAN, payload),
        "SNAN": BfpValue(fmt, negative, FloatKind.SNAN, payload),
        "MAX": BfpValue(
            fmt, negative, FloatKind.FINITE, 2**fmt.precision - 1, fmt.quantum_max
        ),
        "MIN": BfpValue(
            fmt, negative, FloatKind.FINITE, 2 ** (fmt.precision - 1), fmt.quantum_min
        ),
        "DMIN": BfpValue(fmt, negative, FloatKind.FINITE, 1, fmt.quantum_min),
    }


def _bfp_special(item: DcItem, text: str, bits: int, origin: Origin) -> BfpValue:
    name = _special_name(text)
    shortest = _BFP_SIGN_BITS + _bfp_exponent_bits(item) + _BFP_NAN_FRACTION_BITS
    if name in _INFINITY_AND_NANS and bits < shortest:
        raise HlasmLoweringError(
            f"{_constant(item, text)} at line {origin.line} of {origin.file}",
            f"a length of at least {shortest} bits",
            f"{bits} bits",
        )
    return _bfp_specials(_bfp_format(item, bits), _negative(text))[name]


def _bfp_number(item: DcItem, text: str, bits: int) -> BfpValue:
    fmt = _bfp_format(item, bits)
    magnitude = _magnitude(item, text)
    if magnitude == 0:
        return BfpValue(fmt, _negative(text), FloatKind.ZERO)
    mode = BFP_MODIFIER_MODES[int(_rounding_code(text, _BFP_DEFAULT_ROUNDING))]
    return rounding_into(fmt, mode).round(_negative(text), magnitude).value


def _bfp(item: DcItem, text: str, bits: int, origin: Origin) -> int:
    if _is_special(text):
        return bfp_image(_bfp_special(item, text, bits, origin))
    return bfp_image(_bfp_number(item, text, bits))


def _dfp_specials(fmt: DfpFormat, negative: bool) -> Mapping[str, DfpValue]:
    return {
        "INF": DfpValue(fmt, negative, FloatKind.INFINITY),
        "NAN": DfpValue(fmt, negative, FloatKind.QNAN),
        "QNAN": DfpValue(fmt, negative, FloatKind.QNAN),
        "SNAN": DfpValue(fmt, negative, FloatKind.SNAN),
        "MAX": DfpValue(
            fmt, negative, FloatKind.FINITE, 10**fmt.precision - 1, fmt.quantum_max
        ),
        "MIN": DfpValue(fmt, negative, FloatKind.FINITE, 1, fmt.emin),
        "DMIN": DfpValue(fmt, negative, FloatKind.FINITE, 1, fmt.quantum_min),
    }


def _dfp_number(item: DcItem, text: str) -> DfpValue:
    fmt = _DFP_FORMATS[item.type]
    whole, _, fraction = _mantissa(text).partition(_DECIMAL_POINT)
    coefficient = int(whole + fraction)
    kind = FloatKind.FINITE if coefficient else FloatKind.ZERO
    exponent = _exponent(item, text) - len(fraction)
    mode = DFP_MODIFIER_MODES[int(_rounding_code(text, _DFP_DEFAULT_ROUNDING))]
    return dfp_fitted(DfpValue(fmt, _negative(text), kind, coefficient, exponent), mode)


def _dfp(item: DcItem, text: str, bits: int, origin: Origin) -> int:
    if _is_special(text):
        fmt = _DFP_FORMATS[item.type]
        return dfp_image(_dfp_specials(fmt, _negative(text))[_special_name(text)])
    return dfp_image(_dfp_number(item, text))


_FAMILIES: Mapping[str, FloatEncoder] = {
    "": _unextended_hfp,
    "H": _extended_hfp,
    "Q": _extended_hfp,
    "B": _bfp,
    "D": _dfp,
}


def floating_point_image(item: DcItem, text: str, bits: int, origin: Origin) -> int:
    return _FAMILIES[item.extension](item, text, bits, origin)
