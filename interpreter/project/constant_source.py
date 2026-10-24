# pyright: standard
"""Where a warned constant was written: in the open code or in a macro."""

from interpreter.project.in_macro import InMacro
from interpreter.project.in_open_code import InOpenCode

type ConstantSource = InMacro | InOpenCode
