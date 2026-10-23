# pyright: standard
"""A radix-conversion source of any radix: its sign, kind, exact magnitude and NaN payload."""

from dataclasses import dataclass
from fractions import Fraction

from zarch_float.float_kind import FloatKind


@dataclass(frozen=True)
class RadixSource:
    negative: bool
    kind: FloatKind
    magnitude: Fraction
    payload: int
