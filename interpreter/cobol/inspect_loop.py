"""The registers and variables an INSPECT scan loop shares across its phrases."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName


@dataclass(frozen=True)
class InspectLoop:
    """The inspected characters and their count, the constant 1, the cursor,
    the nearest match offered so far and the phrase offering it, and the loop
    head a match returns to."""

    source: Register
    size: Register
    one: Register
    cursor: VarName
    best: VarName
    winner: VarName
    head: CodeLabel
