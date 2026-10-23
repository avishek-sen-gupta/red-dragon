# pyright: standard
"""A fixed-point conversion builtin's result in the floating-point result-list layout: the integer image, unreachable scaled fields, the IEEE words and the CC, 3 when invalid and otherwise the source's sign CC."""

from interpreter.hlasm.ieee_words import ieee_words
from zarch_float.condition import Condition
from zarch_float.integer_format import IntegerFormat
from zarch_float.integer_result import IntegerResult

INVALID_CC = 3
UNREACHABLE_SCALED = (0, 0, 0)


def sign_cc(zero: bool, negative: bool) -> int:
    return (not zero) * (2 - negative)


def integer_outcome(
    source_cc: int, result: IntegerResult, target: IntegerFormat
) -> list[int]:
    invalid = Condition.INVALID in result.conditions
    return [
        result.value & (target.maximum - target.minimum),
        0,
        0,
        *UNREACHABLE_SCALED,
        *ieee_words(result.conditions, frozenset()),
        INVALID_CC if invalid else source_cc,
    ]
