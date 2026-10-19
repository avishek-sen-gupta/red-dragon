"""WRITE ... BEFORE|AFTER ADVANCING n LINES: the device advances n lines."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.advancing_position import AdvancingPosition
from cobol_asg.cobol_expression import ExprNode


@dataclass(frozen=True)
class AdvancingLines:
    position: AdvancingPosition
    lines: ExprNode
