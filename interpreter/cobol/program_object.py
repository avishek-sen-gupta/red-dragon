"""The convention by which a COBOL program registers itself and a CALL finds it."""

from __future__ import annotations

from cobol_asg.asg_types import CobolASG
from cobol_asg.contained_programs import UNNAMED_PROGRAM
from interpreter.field_name import FieldName
from interpreter.var_name import VarName

ENTRY_PREFIX = "__entry_"
PROGRAM_PREFIX = "__prog_"
ARGUMENTS_PARAM = VarName("__call_arguments")
WORKING_STORAGE_FIELD = FieldName("ws_handle")
INITIAL_STATE_FIELD = FieldName("initial_state")


def entry_var(program_id: str) -> VarName:
    return VarName(f"{ENTRY_PREFIX}{program_id.upper()}")


def program_var(program_id: str) -> VarName:
    return VarName(f"{PROGRAM_PREFIX}{program_id.upper()}")


def file_area_var(program_id: str) -> VarName:
    """The variable holding the program's FILE SECTION region, allocated once."""
    return VarName(f"__file_area_{program_id.upper()}")


def use_request_var(program_id: str) -> VarName:
    """The variable naming the USE GLOBAL section a contained program asks the
    program to run, empty when none is asked for."""
    return VarName(f"__use_request_{program_id.upper()}")


def program_name(asg: CobolASG) -> str:
    return (asg.program_id or UNNAMED_PROGRAM).upper()
