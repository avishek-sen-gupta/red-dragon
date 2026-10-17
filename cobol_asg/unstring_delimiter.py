"""One UNSTRING DELIMITED BY / OR operand and whether ALL precedes it."""

from dataclasses import dataclass

from cobol_asg.ref_mod import RefModOperand


@dataclass(frozen=True)
class UnstringDelimiter:
    operand: RefModOperand
    all: bool = False
