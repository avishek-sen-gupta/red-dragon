# pyright: standard
"""BFP TEST DATA CLASS: the second-operand bit for an operand's class and sign (PoO figure 19-26)."""

from collections.abc import Mapping

from zarch_float.bfp_value import BfpValue
from zarch_float.float_kind import FloatKind

_LAST_BIT = 11
_SUBNORMAL_CLASS = 2
_CLASSES: Mapping[FloatKind, int] = {
    FloatKind.ZERO: 0,
    FloatKind.FINITE: 1,
    FloatKind.INFINITY: 3,
    FloatKind.QNAN: 4,
    FloatKind.SNAN: 5,
}


def _class(a: BfpValue) -> int:
    subnormal = (
        a.kind is FloatKind.FINITE and a.significand >> (a.format.precision - 1) == 0
    )
    return _SUBNORMAL_CLASS if subnormal else _CLASSES[a.kind]


def bfp_test_data_class(a: BfpValue, mask: int) -> bool:
    return bool(mask >> (_LAST_BIT - 2 * _class(a) - int(a.negative)) & 1)
