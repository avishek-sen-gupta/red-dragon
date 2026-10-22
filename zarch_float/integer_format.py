# pyright: standard
"""A fixed-point target range; out-of-range and NaN sources deliver an end of it."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegerFormat:
    minimum: int
    maximum: int

    def clamp(self, value: int) -> int:
        return min(max(value, self.minimum), self.maximum)

    def holds(self, value: int) -> bool:
        return self.minimum <= value <= self.maximum


SIGNED_32 = IntegerFormat(-(2**31), 2**31 - 1)
SIGNED_64 = IntegerFormat(-(2**63), 2**63 - 1)
UNSIGNED_32 = IntegerFormat(0, 2**32 - 1)
UNSIGNED_64 = IntegerFormat(0, 2**64 - 1)
