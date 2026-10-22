# pyright: standard
"""Runs a decimal operation into a DFP format: PoO figures 20-5 and 20-6, tininess first."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction

from zarch_float.condition import Condition, raised
from zarch_float.dfp_context import (
    DecimalOperation,
    bounded,
    from_decimal,
    raised_in,
    unbounded,
)
from zarch_float.dfp_format import EXTENDED, LONG, DfpFormat
from zarch_float.dfp_result import DfpResult
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind
from zarch_float.rounding_mode import RoundingMode

_TRAP_SCALE: Mapping[DfpFormat, int] = {LONG: 576, EXTENDED: 9216}
_TRAPPED = frozenset({Condition.OVERFLOW, Condition.TINY})
_ROUNDING = frozenset({Condition.INEXACT, Condition.INCREMENTED})

type Exact = Callable[[], Fraction]


def _incremented(
    value: DfpValue, conditions: frozenset[Condition], exact: Exact
) -> bool:
    if Condition.INEXACT not in conditions:
        return False
    return value.kind is FloatKind.INFINITY or value.magnitude() > abs(exact())


def _with_increment(
    value: DfpValue, conditions: frozenset[Condition], exact: Exact
) -> frozenset[Condition]:
    increment = raised((Condition.INCREMENTED, _incremented(value, conditions, exact)))
    return conditions | increment


@dataclass(frozen=True)
class DfpRounding:
    target: DfpFormat
    mode: RoundingMode
    trap_format: DfpFormat
    trap_scale: int

    def apply(self, operation: DecimalOperation, exact: Exact) -> DfpResult:
        context = bounded(self.target, self.mode)
        value = from_decimal(operation(context), self.target)
        conditions = _with_increment(value, raised_in(context), exact)
        if conditions & _TRAPPED:
            return self._trapped(operation, exact, value, conditions)
        return DfpResult(value, conditions, value, conditions & _ROUNDING)

    def _trapped(
        self,
        operation: DecimalOperation,
        exact: Exact,
        value: DfpValue,
        conditions: frozenset[Condition],
    ) -> DfpResult:
        context = unbounded(self.target.precision, self.mode)
        precise = operation(context)
        direction = int(Condition.TINY in conditions) - int(
            Condition.OVERFLOW in conditions
        )
        shifted = precise.scaleb(direction * self.trap_scale, context)
        scaled = from_decimal(shifted, self.trap_format)
        precise_value = from_decimal(precise, self.trap_format)
        scaled_conditions = _with_increment(precise_value, raised_in(context), exact)
        return DfpResult(value, conditions, scaled, scaled_conditions & _ROUNDING)


def dfp_rounding_into(target: DfpFormat, mode: RoundingMode) -> DfpRounding:
    return DfpRounding(target, mode, target, _TRAP_SCALE[target])
