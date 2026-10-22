# pyright: standard
"""Rounds an exact nonzero value into a BFP format: PoO figure 19-9, tininess before rounding."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction

from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_result import BfpResult
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition, raised
from zarch_float.exact_rounding import round_ratio
from zarch_float.float_kind import FloatKind
from zarch_float.rounding_mode import RoundingMode

_OVERFLOWS_TO_INFINITY: Mapping[RoundingMode, Callable[[bool], bool]] = {
    RoundingMode.NEAREST_EVEN: lambda _: True,
    RoundingMode.NEAREST_AWAY: lambda _: True,
    RoundingMode.NEAREST_TOWARD_ZERO: lambda _: True,
    RoundingMode.AWAY_FROM_ZERO: lambda _: True,
    RoundingMode.TOWARD_ZERO: lambda _: False,
    RoundingMode.PREPARE_SHORTER: lambda _: False,
    RoundingMode.TOWARD_POSITIVE: lambda negative: not negative,
    RoundingMode.TOWARD_NEGATIVE: lambda negative: negative,
}


def leading_exponent(magnitude: Fraction) -> int:
    estimate = magnitude.numerator.bit_length() - magnitude.denominator.bit_length()
    return estimate - int(magnitude < Fraction(2) ** estimate)


def _finite(
    target: BfpFormat, negative: bool, significand: int, exponent: int
) -> BfpValue:
    if significand == 0:
        return BfpValue(target, negative, FloatKind.ZERO)
    carry = significand >> target.precision
    return BfpValue(
        target, negative, FloatKind.FINITE, significand >> carry, exponent + carry
    )


@dataclass(frozen=True)
class BfpRounding:
    target: BfpFormat
    mode: RoundingMode
    trap_format: BfpFormat
    trap_scale: int

    def round(self, negative: bool, magnitude: Fraction) -> BfpResult:
        top = leading_exponent(magnitude)
        precise = self._at(negative, magnitude, top - self.target.precision + 1)
        if precise[0].exponent > self.target.quantum_max:
            return self._overflow(negative, precise)
        if top < self.target.emin:
            return self._tiny(negative, magnitude, precise)
        return BfpResult(precise[0], precise[1], precise[0], precise[1])

    def _at(
        self, negative: bool, magnitude: Fraction, quantum: int
    ) -> tuple[BfpValue, frozenset[Condition]]:
        scaled = magnitude / Fraction(2) ** quantum
        rounded = round_ratio(scaled.numerator, scaled.denominator, self.mode, negative)
        flags = raised(
            (Condition.INEXACT, rounded.inexact),
            (Condition.INCREMENTED, rounded.incremented),
        )
        return _finite(self.target, negative, rounded.magnitude, quantum), flags

    def _overflow(
        self, negative: bool, precise: tuple[BfpValue, frozenset[Condition]]
    ) -> BfpResult:
        infinite = _OVERFLOWS_TO_INFINITY[self.mode](negative)
        largest = BfpValue(
            self.target,
            negative,
            FloatKind.FINITE,
            2**self.target.precision - 1,
            self.target.quantum_max,
        )
        value = (
            BfpValue(self.target, negative, FloatKind.INFINITY) if infinite else largest
        )
        conditions = raised(
            (Condition.OVERFLOW, True),
            (Condition.INEXACT, True),
            (Condition.INCREMENTED, infinite),
        )
        return BfpResult(value, conditions, self._scaled(precise[0], -1), precise[1])

    def _tiny(
        self,
        negative: bool,
        magnitude: Fraction,
        precise: tuple[BfpValue, frozenset[Condition]],
    ) -> BfpResult:
        value, flags = self._at(negative, magnitude, self.target.quantum_min)
        conditions = flags | raised(
            (Condition.TINY, True), (Condition.UNDERFLOW, Condition.INEXACT in flags)
        )
        return BfpResult(value, conditions, self._scaled(precise[0], 1), precise[1])

    def _scaled(self, precise: BfpValue, direction: int) -> BfpValue:
        widening = self.trap_format.precision - self.target.precision
        return BfpValue(
            self.trap_format,
            precise.negative,
            FloatKind.FINITE,
            precise.significand << widening,
            precise.exponent - widening + direction * self.trap_scale,
        )


def rounding_into(target: BfpFormat, mode: RoundingMode) -> BfpRounding:
    return BfpRounding(target, mode, target, target.trap_scale)
