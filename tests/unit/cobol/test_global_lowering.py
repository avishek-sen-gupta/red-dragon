"""How a contained program lowers a reference to a global name of a program that
contains it (red-dragon-ljku.4): its procedure's entry loads the containing program's
WORKING-STORAGE from that program's object and its FILE SECTION region from that
program's variable, and the reference is a write at the item's offset there."""

import json
from collections.abc import Sequence
from pathlib import Path

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.compilation_unit import programs_in_preorder
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.program_object import (
    WORKING_STORAGE_FIELD,
    file_area_var,
    program_var,
)
from interpreter.instructions import (
    Const,
    InstructionBase,
    Label_,
    LoadField,
    LoadVar,
    StoreVar,
    WriteRegion,
)
from interpreter.ir import CodeLabel
from interpreter.register import Register
from tests.covers import covers

_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. OUTER.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SHARED-FILE ASSIGN TO SHAREDDD.
       DATA DIVISION.
       FILE SECTION.
       FD  SHARED-FILE GLOBAL.
       01  SHARED-REC     PIC X(6).
       WORKING-STORAGE SECTION.
       01  OWN-FIRST      PIC X(3).
       01  G-VAL  GLOBAL  PIC X(2).
       PROCEDURE DIVISION.
           STOP RUN.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INNER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  OWN-FIRST      PIC X(3).
       PROCEDURE DIVISION.
           MOVE 'IN' TO G-VAL.
           MOVE 'RECORD' TO SHARED-REC.
           GOBACK.
       END PROGRAM INNER.
       END PROGRAM OUTER.
"""


def _lowered(
    tmp_path: Path,
) -> tuple[list[InstructionBase], list[InstructionBase]]:
    """OUTER's IR, and INNER's from its procedure's label on."""
    written = make_cobol_parser().parse_to_file(_SOURCE, tmp_path / "unit.json")
    outer, inner = (
        CobolFrontend(make_cobol_parser()).lower_from_ast_dict(program)
        for program in programs_in_preorder(json.loads(written.read_text()))
    )
    return outer, inner[inner.index(Label_(label=CodeLabel("func_inner_0"))) :]


def _origins(ir: Sequence[InstructionBase]) -> dict[Register, str]:
    """What each region register in the procedure was loaded from."""
    singletons = {
        i.result_reg: str(i.name)
        for i in ir
        if isinstance(i, LoadVar) and i.name == program_var("OUTER")
    }
    return {
        **{
            i.result_reg: f"{singletons[i.obj_reg]}.{i.field_name}"
            for i in ir
            if isinstance(i, LoadField)
            and i.obj_reg in singletons
            and i.field_name == WORKING_STORAGE_FIELD
        },
        **{
            i.result_reg: str(i.name)
            for i in ir
            if isinstance(i, LoadVar) and str(i.name).startswith("__file_area_")
        },
    }


@covers(CobolFeature.GLOBAL_DATA, CobolFeature.GLOBAL_FILE)
def test_a_global_reference_writes_into_the_containing_programs_storage(tmp_path):
    load, procedure = _lowered(tmp_path)
    origins = _origins(procedure)
    consts = {i.result_reg: i.value for i in procedure if isinstance(i, Const)}

    assert (
        [
            (origins[i.region_reg], consts[i.offset_reg], i.length)
            for i in procedure
            if isinstance(i, WriteRegion) and i.region_reg in origins
        ],
        [
            str(i.name)
            for i in load
            if isinstance(i, StoreVar) and i.name == file_area_var("OUTER")
        ],
    ) == (
        [("__prog_OUTER.ws_handle", 3, 2), ("__file_area_OUTER", 0, 6)],
        ["__file_area_OUTER"],
    )
