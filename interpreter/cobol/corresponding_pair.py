"""An item of a CORRESPONDING sending group and its counterpart in the receiving group, each as a qualified, subscripted operand."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.ref_mod import RefModOperand


@dataclass(frozen=True)
class CorrespondingPair:
    source: RefModOperand
    target: RefModOperand
