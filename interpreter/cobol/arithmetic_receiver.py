"""A resolved receiving field of an arithmetic verb: its operand, field reference and region."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.register import Register


@dataclass(frozen=True)
class ArithmeticReceiver:
    operand: RefModOperand
    ref: ResolvedFieldRef
    region: Register
