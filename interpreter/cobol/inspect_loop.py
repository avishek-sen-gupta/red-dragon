"""One iteration of an INSPECT scan loop: the phrases competing and the nearest match so far."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.cobol.inspect_matching import InspectMatching
from interpreter.ir import CodeLabel
from interpreter.var_name import VarName


@dataclass(frozen=True)
class InspectLoop:
    """The phrases the scan offers, the nearest match offered so far and the
    phrase offering it, and the loop head a match returns to."""

    matching: InspectMatching
    best: VarName
    winner: VarName
    head: CodeLabel
