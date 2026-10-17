"""An elementary item an INITIALIZE operand moves into, as a qualified, subscripted operand."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.data_layout import FieldLayout


@dataclass(frozen=True)
class InitializeTarget:
    storage: FieldLayout
    operand: RefModOperand
