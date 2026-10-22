# pyright: standard
"""One interlocked comparison: a comparison value against an operand, and the place the operand replaces when they differ."""

from dataclasses import dataclass

from interpreter.hlasm.place import Place


@dataclass(frozen=True)
class Comparison:
    value: Place
    operand: Place
    refreshed: Place
