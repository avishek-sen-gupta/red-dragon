# pyright: standard
"""A DIVIDE TO INTEGER outcome: the remainder result, the integer quotient, and whether it is partial or overflowed."""

from dataclasses import dataclass

from zarch_float.bfp_result import BfpResult
from zarch_float.bfp_value import BfpValue


@dataclass(frozen=True)
class BfpDivideToIntegerResult:
    remainder: BfpResult
    quotient: BfpValue
    partial: bool
    quotient_overflow: bool
