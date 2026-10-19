"""WRITE ... BEFORE|AFTER ADVANCING mnemonic-name: a skip to a carriage-control channel."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.advancing_position import AdvancingPosition


@dataclass(frozen=True)
class AdvancingMnemonic:
    position: AdvancingPosition
    mnemonic: str
