# pyright: standard
"""Parses one E, D or L nominal value (already checked by the bridge) into a typed number or special value."""

from collections.abc import Mapping

from hlasm_asg.program.dc_item import DcItem
from interpreter.hlasm.float_number import FloatNumber
from interpreter.hlasm.float_special import FloatSpecial
from interpreter.hlasm.float_special_value import FloatSpecialValue

type FloatNominal = FloatNumber | FloatSpecial

_SPACE = " "
_MINUS = "-"
_SIGNS = "+-"
_OPEN = "("
_PARENTHESES = "()"
_ROUNDING = "R"
_EXPONENT = "E"
_DECIMAL_POINT = "."
_DEFAULT_ROUNDING: Mapping[str, int] = {"": 1, "H": 1, "Q": 1, "B": 4, "D": 8}


def _split(text: str, separator: str) -> tuple[str, str]:
    before, _, after = text.partition(separator)
    return before, after


def _number(item: DcItem, negative: bool, body: str) -> FloatNumber:
    written, rounding = _split(body, _ROUNDING)
    mantissa, exponent = _split(written, _EXPONENT)
    whole, fraction = _split(mantissa, _DECIMAL_POINT)
    return FloatNumber(
        negative,
        int(whole + fraction),
        len(fraction),
        int(exponent or "0") + item.exponent,
        int(rounding or _DEFAULT_ROUNDING[item.extension]),
    )


def parse_float_nominal(item: DcItem, text: str) -> FloatNominal:
    cleaned = text.replace(_SPACE, "").upper()
    negative = cleaned.startswith(_MINUS)
    body = cleaned.lstrip(_SIGNS)
    if body.startswith(_OPEN):
        return FloatSpecial(negative, FloatSpecialValue(body.strip(_PARENTHESES)))
    return _number(item, negative, body)
