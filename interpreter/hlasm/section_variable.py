# pyright: standard
"""The variable holding a section's run-time address, qualified by the module that names it."""

from interpreter.hlasm.hlasm_constants import SECTION_VAR_PREFIX
from interpreter.var_name import VarName


def section_var(module: str, section: str) -> VarName:
    return VarName(f"{SECTION_VAR_PREFIX}{module}.{section}")
