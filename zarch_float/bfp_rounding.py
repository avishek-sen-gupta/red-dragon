# pyright: standard
"""Rounds an exact nonzero value into a BFP format: PoO figure 19-9, tininess before rounding. With one bit of precision both candidates of a tie have significand 1, so round to nearest even takes the one whose image is even (its biased exponent), our ruling."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction

from zarch_float.bfp_format import BfpFormat
from zarch_float.bfp_result import BfpResult
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition, raised
from zarch_float.exact_rounding import leading_exponent, round_ratio
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

_ONE_BIT_TIES: Mapping[int, RoundingMode] = {
    0: RoundingMode.NEAREST_TOWARD_ZERO,
    1: RoundingMode.NEAREST_AWAY,
}


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
        mode = self._tie_mode(top)
        precise = self._at(negative, magnitude, top - self.target.precision + 1, mode)
        if precise[0].exponent > self.target.quantum_max:
            return self._overflow(negative, precise)
        if top < self.target.emin:
            return self._tiny(negative, magnitude, precise, mode)
        return BfpResult(precise[0], precise[1], precise[0], precise[1])

    def _tie_mode(self, top: int) -> RoundingMode:
        if self.mode is not RoundingMode.NEAREST_EVEN or self.target.precision > 1:
            return self.mode
        lower_biased_exponent = top + self.target.emax
        return _ONE_BIT_TIES[lower_biased_exponent % 2]

    def _at(
        self, negative: bool, magnitude: Fraction, quantum: int, mode: RoundingMode
    ) -> tuple[BfpValue, frozenset[Condition]]:
        scaled = magnitude / Fraction(2) ** quantum
        rounded = round_ratio(scaled.numerator, scaled.denominator, mode, negative)
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
        mode: RoundingMode,
    ) -> BfpResult:
        value, flags = self._at(negative, magnitude, self.target.quantum_min, mode)
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
