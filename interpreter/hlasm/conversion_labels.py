# pyright: standard
"""Where a Unicode conversion step goes: the next step, the three ends, and the encoder's entries for a basic-plane or a supplementary character."""

from dataclasses import dataclass

from interpreter.ir import CodeLabel


@dataclass(frozen=True)
class ConversionLabels:
    loop: CodeLabel
    exhausted: CodeLabel
    invalid: CodeLabel
    full: CodeLabel
    basic: CodeLabel
    supplementary: CodeLabel
