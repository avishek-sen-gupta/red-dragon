"""A START or a keyed READ of a file with alternate record keys tells the provider which
key becomes the key of reference, by the leftmost position its KEY data item shares
with a declared key, just before the access; a file without alternate keys, and a
sequential READ, say nothing."""

from __future__ import annotations

import json
from pathlib import Path

from cobol_asg.compilation_unit import programs_in_preorder
from interpreter.cobol.features import CobolFeature
from interpreter.frontend import make_cobol_parser
from interpreter.instructions import CallFunction, Const, InstructionBase
from interpreter.project.cobol_compile import compile_cobol_module
from interpreter.register import Register
from tests.covers import covers

_ACCESSES = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PGMK.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT AX ASSIGN TO AXDD ORGANIZATION INDEXED
               ACCESS DYNAMIC RECORD KEY AX-ID
               ALTERNATE RECORD KEY AX-ALT1
               ALTERNATE RECORD KEY AX-ALT2 WITH DUPLICATES.
           SELECT PX ASSIGN TO PXDD ORGANIZATION INDEXED
               ACCESS DYNAMIC RECORD KEY PX-ID.
       DATA DIVISION.
       FILE SECTION.
       FD  AX.
       01  AX-REC.
           05  AX-ID   PIC X(2).
           05  AX-ALT1 PIC X(2).
           05  AX-ALT2 PIC X(2).
       01  AX-OTHER.
           05  FILLER  PIC X(4).
           05  AX-LEAD PIC X(1).
       FD  PX.
       01  PX-REC.
           05  PX-ID   PIC X(3).
       PROCEDURE DIVISION.
           START AX KEY IS > AX-ALT2.
           START AX.
           READ AX KEY IS AX-ALT1.
           READ AX.
           READ AX NEXT.
           START AX KEY IS NOT < AX-LEAD.
           START PX KEY IS > PX-ID.
           READ PX KEY IS PX-ID.
           GOBACK.
"""

_ACCESS = frozenset({"__cobol_start_file", "__cobol_read_record"})
_REFER = "__cobol_key_of_reference"


def _accesses(ir: tuple[InstructionBase, ...]) -> list[tuple[str, str]]:
    constants = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        (
            str(i.func_name),
            (
                f"{constants[Register(str(i.args[0]))]}"
                f"={constants[Register(str(i.args[1]))]}"
                if str(i.func_name) == _REFER
                else str(constants[Register(str(i.args[0]))])
            ),
        )
        for i in ir
        if isinstance(i, CallFunction) and str(i.func_name) in _ACCESS | {_REFER}
    ]


@covers(CobolFeature.START)
def test_start_and_keyed_read_name_the_key_of_reference(tmp_path: Path) -> None:
    parser = make_cobol_parser()
    ast_path = tmp_path / "program.ast.json"
    parser.parse_to_file(_ACCESSES, ast_path)
    ir = compile_cobol_module(
        _ACCESSES,
        parser=parser,
        program=programs_in_preorder(json.loads(ast_path.read_text()))[0],
    ).ir
    assert _accesses(ir) == [
        (_REFER, "AX=2"),
        ("__cobol_start_file", "AX"),
        (_REFER, "AX=0"),
        ("__cobol_start_file", "AX"),
        (_REFER, "AX=1"),
        ("__cobol_read_record", "AX"),
        (_REFER, "AX=0"),
        ("__cobol_read_record", "AX"),
        ("__cobol_read_record", "AX"),
        (_REFER, "AX=2"),
        ("__cobol_start_file", "AX"),
        ("__cobol_start_file", "PX"),
        ("__cobol_read_record", "PX"),
    ]
