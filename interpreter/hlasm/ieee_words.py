# pyright: standard
"""The FPC bit of each IEEE condition, and the trap, flag and DXC words a floating-point builtin reports for the trap ladder (ruling R43)."""

from collections.abc import Mapping

from interpreter.hlasm.bfp_slots import (
    DIVISION_BY_ZERO_BIT,
    INCREMENTED_BIT,
    INEXACT_BIT,
    INVALID_BIT,
    OVERFLOW_BIT,
    QUANTUM_BIT,
    UNDERFLOW_BIT,
)
from zarch_float.condition import Condition

type _Bits = Mapping[Condition, int]

_TRAPS: _Bits = {
    Condition.INVALID: INVALID_BIT,
    Condition.DIVISION_BY_ZERO: DIVISION_BY_ZERO_BIT,
    Condition.OVERFLOW: OVERFLOW_BIT,
    Condition.TINY: UNDERFLOW_BIT,
    Condition.INEXACT: INEXACT_BIT,
    Condition.QUANTUM: QUANTUM_BIT,
}
_FLAGS: _Bits = {
    Condition.INVALID: INVALID_BIT,
    Condition.DIVISION_BY_ZERO: DIVISION_BY_ZERO_BIT,
    Condition.OVERFLOW: OVERFLOW_BIT,
    Condition.UNDERFLOW: UNDERFLOW_BIT,
    Condition.INEXACT: INEXACT_BIT,
    Condition.QUANTUM: QUANTUM_BIT,
}
_SCALINGS: _Bits = {Condition.OVERFLOW: OVERFLOW_BIT, Condition.TINY: UNDERFLOW_BIT}
_DETAILS: _Bits = {
    Condition.INEXACT: INEXACT_BIT,
    Condition.INCREMENTED: INCREMENTED_BIT,
}


def _bits(conditions: frozenset[Condition], bits: _Bits) -> int:
    return sum(bit for condition, bit in bits.items() if condition in conditions)


def ieee_words(
    conditions: frozenset[Condition], scaled_conditions: frozenset[Condition]
) -> list[int]:
    scaling = _bits(conditions, _SCALINGS)
    scaled_detail = _bits(scaled_conditions, _DETAILS) * bool(scaling)
    return [
        _bits(conditions, _TRAPS),
        _bits(conditions, _FLAGS),
        scaling | scaled_detail,
        _bits(conditions, _DETAILS),
    ]
