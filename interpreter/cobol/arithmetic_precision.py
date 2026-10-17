"""The statement-level precision an arithmetic expression is evaluated with."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArithmeticPrecision:
    dmax: int
    floating: bool
