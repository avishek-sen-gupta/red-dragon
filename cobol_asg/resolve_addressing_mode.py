"""Turns an LP setting into its AddressingMode, once, where it is chosen."""

from __future__ import annotations

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.lp import LP
from cobol_asg.lp32 import Lp32
from cobol_asg.lp64 import Lp64


def addressing_mode(lp: LP) -> AddressingMode:
    return {LP.LP32: Lp32(), LP.LP64: Lp64()}[lp]
