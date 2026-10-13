"""The convention by which a COBOL program registers itself and a CALL finds it."""

from __future__ import annotations

from interpreter.field_name import FieldName
from interpreter.var_name import VarName

ENTRY_PREFIX = "__entry_"
PROGRAM_PREFIX = "__prog_"
ARGUMENTS_PARAM = VarName("__call_arguments")
WORKING_STORAGE_FIELD = FieldName("ws_handle")


def entry_var(program_id: str) -> VarName:
    return VarName(f"{ENTRY_PREFIX}{program_id.upper()}")


def program_var(program_id: str) -> VarName:
    return VarName(f"{PROGRAM_PREFIX}{program_id.upper()}")
