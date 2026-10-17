"""OPEN hands the provider each file's attributes from its SELECT entry and FD: record
length (its longest record), organization, prime key extent within the file's own
record, access mode, RELATIVE KEY digits and OPTIONAL."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.frontend import make_cobol_parser
from interpreter.instructions import CallFunction, Const, InstructionBase
from interpreter.project.cobol_compile import compile_cobol_module
from interpreter.register import Register
from tests.covers import covers

_THREE_FILES = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PGMX.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SQ ASSIGN TO SQDD.
           SELECT OPTIONAL IX ASSIGN TO IXDD ORGANIZATION INDEXED
               ACCESS SEQUENTIAL RECORD KEY IX-ID.
           SELECT RL ASSIGN TO RLDD ORGANIZATION RELATIVE
               ACCESS RANDOM RELATIVE KEY RL-NO.
       DATA DIVISION.
       FILE SECTION.
       FD  SQ.
       01  SQ-REC PIC X(10).
       01  SQ-LONG PIC X(14).
       FD  IX.
       01  IX-REC.
           05  IX-TAG  PIC X(3).
           05  IX-ID   PIC X(4).
           05  IX-DATA PIC X(5).
       FD  RL.
       01  RL-REC PIC X(6).
       WORKING-STORAGE SECTION.
       01  RL-NO PIC 9(3).
       PROCEDURE DIVISION.
           OPEN INPUT SQ IX RL.
           GOBACK.
"""


def _open_arguments(
    ir: tuple[InstructionBase, ...],
) -> list[tuple[str | int, ...]]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        tuple(consts[Register(str(a))] for a in i.args)
        for i in ir
        if isinstance(i, CallFunction) and str(i.func_name) == "__cobol_open_file"
    ]


@covers(CobolFeature.OPEN)
def test_open_passes_each_files_attributes(tmp_path: Path) -> None:
    parser = make_cobol_parser()
    ast_path = tmp_path / "program.ast.json"
    parser.parse_to_file(_THREE_FILES, ast_path)
    ir = compile_cobol_module(_THREE_FILES, parser=parser, ast_path=ast_path).ir
    assert _open_arguments(ir) == [
        ("SQ", "INPUT", 14, "SEQUENTIAL", 0, 0, "SEQUENTIAL", 0, False, "PGMX"),
        ("IX", "INPUT", 12, "INDEXED", 3, 4, "SEQUENTIAL", 0, True, "PGMX"),
        ("RL", "INPUT", 6, "RELATIVE", 0, 0, "RANDOM", 3, False, "PGMX"),
    ]
