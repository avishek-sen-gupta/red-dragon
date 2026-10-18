"""How a program's EXTERNAL record and EXTERNAL file lower (red-dragon-ljku.3): at load,
each area is found in the run unit's directory by name and allocated when absent, and an
EXTERNAL file's connector starts closed there; on entry the procedure loads each area's
region from the directory, and its fields are addressed from the area's start."""

from collections.abc import Sequence

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.external_area import ExternalKind, external_directory
from interpreter.cobol.features import CobolFeature
from interpreter.instructions import (
    AllocRegion,
    BranchIf,
    CallFunction,
    Const,
    InstructionBase,
    Label_,
    LoadField,
    LoadVar,
    StoreField,
    StoreVar,
    WriteRegion,
)
from interpreter.ir import CodeLabel
from interpreter.register import Register
from tests.covers import covers

_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXTU.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SHARED-FILE ASSIGN TO SHAREDDD.
           SELECT OWN-FILE ASSIGN TO OWNDD.
       DATA DIVISION.
       FILE SECTION.
       FD  OWN-FILE.
       01  OWN-REC          PIC X(10).
       FD  SHARED-FILE IS EXTERNAL.
       01  SHARED-REC       PIC X(6).
       01  SHARED-LONG      PIC X(9).
       WORKING-STORAGE SECTION.
       01  WS-FIRST         PIC X(3).
       01  SHARED-AREA IS EXTERNAL.
           05  SH-TEXT      PIC X(4).
           05  SH-NUM       PIC 9(4).
       PROCEDURE DIVISION.
           MOVE 5 TO SH-NUM.
           MOVE 'X' TO SHARED-LONG.
           STOP RUN.
"""

_PROCEDURE = CodeLabel("func_extu_0")


def _lowered() -> tuple[list[InstructionBase], list[InstructionBase]]:
    ir = CobolFrontend(make_cobol_parser()).lower(_SOURCE)
    split = ir.index(Label_(label=_PROCEDURE))
    return ir[:split], ir[split:]


def _consts(ir: Sequence[InstructionBase]) -> dict[Register, object]:
    return {i.result_reg: i.value for i in ir if isinstance(i, Const)}


def _directories(ir: Sequence[InstructionBase]) -> dict[Register, ExternalKind]:
    kinds = {external_directory(kind): kind for kind in ExternalKind}
    return {
        i.result_reg: kinds[i.name]
        for i in ir
        if isinstance(i, LoadVar) and i.name in kinds
    }


def _allocations(
    load: Sequence[InstructionBase],
) -> list[tuple[str, object, object, str, bool]]:
    """For each probe of a directory: its kind, the name probed, the size the region
        allocated next is given, the name that region is stored under, and whether the
    probe's answer is what skips the allocation."""
    consts, dirs = _consts(load), _directories(load)
    return [
        (
            dirs[probe.args[0]].value,
            consts[probe.args[1]],
            consts[_next(load, at, AllocRegion).size_reg],
            str(_next(load, at, StoreField).field_name),
            _next(load, at, BranchIf).cond_reg == probe.result_reg,
        )
        for at, probe in enumerate(load)
        if isinstance(probe, CallFunction)
        and str(probe.func_name) == "dict_contains_key"
    ]


def _next[T: InstructionBase](
    ir: Sequence[InstructionBase], after: int, kind: type[T]
) -> T:
    return next(i for i in ir[after:] if isinstance(i, kind))


@covers(CobolFeature.EXTERNAL_DATA, CobolFeature.EXTERNAL_FILE)
def test_each_external_area_is_allocated_once_by_name_and_bound_on_entry():
    load, procedure = _lowered()
    proc_dirs = _directories(procedure)
    bound = {
        i.result_reg: (proc_dirs[i.obj_reg].value, str(i.field_name))
        for i in procedure
        if isinstance(i, LoadField) and i.obj_reg in proc_dirs
    }
    consts = _consts(procedure)
    writes = [
        (bound[i.region_reg], consts[i.offset_reg], i.length)
        for i in procedure
        if isinstance(i, WriteRegion) and i.region_reg in bound
    ]
    state_vars = sorted(
        str(i.name)
        for i in load
        if isinstance(i, StoreVar) and str(i.name).endswith("_mode")
    )

    assert (_allocations(load), sorted(bound.values()), writes, state_vars) == (
        [
            ("record", "SHARED-AREA", 8, "SHARED-AREA", True),
            ("file", "SHARED-FILE", 9, "SHARED-FILE", True),
        ],
        [("file", "SHARED-FILE"), ("record", "SHARED-AREA")],
        [(("record", "SHARED-AREA"), 4, 4), (("file", "SHARED-FILE"), 0, 9)],
        [
            "__cobol_external_file_SHARED-FILE_mode",
            "__cobol_file_EXTU_OWN-FILE_mode",
        ],
    )
