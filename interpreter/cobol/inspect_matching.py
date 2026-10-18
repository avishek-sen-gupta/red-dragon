"""The phrases one INSPECT scan looks for and what a match of any of them does."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.cobol.inspect_phrase_scan import InspectPhraseScan
from interpreter.register import Register
from interpreter.var_name import VarName

type MatchAction = Callable[[int, InspectPhraseScan, Register], None]


@dataclass(frozen=True)
class InspectMatching:
    """The prepared phrases in written order with their index constants, the
    action applied to the winning phrase's match, and the scan cursor."""

    scans: tuple[InspectPhraseScan, ...]
    indexes: tuple[Register, ...]
    act: MatchAction
    cursor: VarName
