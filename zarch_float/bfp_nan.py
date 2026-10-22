# pyright: standard
"""BFP NaN results: the first SNaN in operand order, quieted, else the first QNaN."""

from collections.abc import Sequence
from dataclasses import replace

from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_result import BfpResult, bfp_exact
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition, raised
from zarch_float.float_kind import FloatKind


def has_nan(operands: Sequence[BfpValue]) -> bool:
    return any(operand.is_nan() for operand in operands)


def propagate_nan(operands: Sequence[BfpValue]) -> BfpResult:
    signaling = [operand for operand in operands if operand.kind is FloatKind.SNAN]
    quiet = [operand for operand in operands if operand.kind is FloatKind.QNAN]
    chosen = [*signaling, *quiet][0]
    return bfp_exact(
        replace(chosen, kind=FloatKind.QNAN),
        raised((Condition.INVALID, bool(signaling))),
    )


def default_nan(target: BfpFormat) -> BfpValue:
    return BfpValue(target, False, FloatKind.QNAN)


def invalid(target: BfpFormat) -> BfpResult:
    return bfp_exact(default_nan(target), frozenset({Condition.INVALID}))
