# pyright: standard
"""DFP NaN results: the first SNaN in operand order, quieted, else the first QNaN."""

from collections.abc import Sequence
from dataclasses import replace

from zarch_float.condition import Condition, raised
from zarch_float.dfp_format import DfpFormat
from zarch_float.dfp_result import DfpResult, dfp_exact
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind


def has_nan(operands: Sequence[DfpValue]) -> bool:
    return any(operand.is_nan() for operand in operands)


def propagate_nan(operands: Sequence[DfpValue]) -> DfpResult:
    signaling = [operand for operand in operands if operand.kind is FloatKind.SNAN]
    quiet = [operand for operand in operands if operand.kind is FloatKind.QNAN]
    chosen = [*signaling, *quiet][0]
    return dfp_exact(
        replace(chosen, kind=FloatKind.QNAN),
        raised((Condition.INVALID, bool(signaling))),
    )


def invalid(target: DfpFormat) -> DfpResult:
    default_nan = DfpValue(target, False, FloatKind.QNAN)
    return dfp_exact(default_nan, frozenset({Condition.INVALID}))
