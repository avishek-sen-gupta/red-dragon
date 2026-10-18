"""The CONVERTING phrase's operands and the loop over its region."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.register import Register
from interpreter.var_name import VarName


@dataclass(frozen=True)
class InspectConverting:
    """The FROM and TO characters, the text being converted, the next position
    to convert and the end of the region."""

    from_chars: Register
    to_chars: Register
    text: VarName
    at: VarName
    end: Register
