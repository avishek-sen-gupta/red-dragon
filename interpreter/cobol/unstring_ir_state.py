"""The variables an UNSTRING examination updates as it acts on each receiver."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.register import Register
from interpreter.var_name import VarName


@dataclass(frozen=True)
class UnstringIrState:
    """The source and its size, the next unexamined position, and the count of
    receivers acted on."""

    source: Register
    size: Register
    position: VarName
    acted: VarName
