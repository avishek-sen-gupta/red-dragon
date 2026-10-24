# pyright: standard
"""A floating-point DC nominal naming a special value, with its sign."""

from dataclasses import dataclass

from interpreter.hlasm.float_special_value import FloatSpecialValue


@dataclass(frozen=True)
class FloatSpecial:
    negative: bool
    value: FloatSpecialValue
