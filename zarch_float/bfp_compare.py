# pyright: standard
"""BFP COMPARE and COMPARE AND SIGNAL: exact ordering, NaNs unordered."""

from fractions import Fraction

from zarch_float.bfp_nan import has_nan
from zarch_float.bfp_value import BfpValue
from zarch_float.comparison import Comparison
from zarch_float.comparison_result import ComparisonResult
from zarch_float.condition import Condition, raised
from zarch_float.float_kind import FloatKind
from zarch_float.ordering import ordered

_SIGNALING = frozenset({FloatKind.SNAN})
_ANY_NAN = frozenset({FloatKind.SNAN, FloatKind.QNAN})


def _rank(value: BfpValue) -> tuple[int, Fraction]:
    if value.kind is FloatKind.INFINITY:
        return (-1 if value.negative else 1), Fraction(0)
    return 0, value.signed()


def _compare(
    a: BfpValue, b: BfpValue, signaling: frozenset[FloatKind]
) -> ComparisonResult:
    if has_nan((a, b)):
        invalid = a.kind in signaling or b.kind in signaling
        return ComparisonResult(
            Comparison.UNORDERED, raised((Condition.INVALID, invalid))
        )
    return ComparisonResult(ordered(_rank(a), _rank(b)), frozenset())


def bfp_compare(a: BfpValue, b: BfpValue) -> ComparisonResult:
    return _compare(a, b, _SIGNALING)


def bfp_compare_signaling(a: BfpValue, b: BfpValue) -> ComparisonResult:
    return _compare(a, b, _ANY_NAN)
