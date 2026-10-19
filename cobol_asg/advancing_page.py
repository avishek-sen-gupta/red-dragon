"""WRITE ... BEFORE|AFTER ADVANCING PAGE: the device advances to the next page."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.advancing_position import AdvancingPosition


@dataclass(frozen=True)
class AdvancingPage:
    position: AdvancingPosition
