"""A program declares each file's frame to the provider once, from its start-up code:
organization, access mode, prime key extent within the file's own record, RELATIVE KEY
digits, OPTIONAL, whether its records vary, and its smallest and longest record. OPEN
then names only the file, the mode and the program."""

from __future__ import annotations

import json
from pathlib import Path

from cobol_asg.file_enums import FileOrganization
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.file_frame import FileFrame, frame_of
from interpreter.cobol.prime_key import PrimeKey
from cobol_asg.compilation_unit import programs_in_preorder
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


def _declared(ir: tuple[InstructionBase, ...]) -> list[tuple[FileFrame, str]]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        (frame_of(consts[Register(str(i.args[0]))]), consts[Register(str(i.args[1]))])
        for i in ir
        if isinstance(i, CallFunction) and str(i.func_name) == "__cobol_declare_file"
    ]


def _opens(ir: tuple[InstructionBase, ...]) -> list[tuple[str, ...]]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        tuple(consts[Register(str(a))] for a in i.args)
        for i in ir
        if isinstance(i, CallFunction) and str(i.func_name) == "__cobol_open_file"
    ]


@covers(CobolFeature.OPEN)
def test_each_file_is_declared_once_and_opened_by_name_and_mode(
    tmp_path: Path,
) -> None:
    parser = make_cobol_parser()
    ast_path = tmp_path / "program.ast.json"
    parser.parse_to_file(_THREE_FILES, ast_path)
    ir = compile_cobol_module(
        _THREE_FILES,
        parser=parser,
        program=programs_in_preorder(json.loads(ast_path.read_text()))[0],
    ).ir
    assert (_declared(ir), _opens(ir)) == (
        [
            (
                FileFrame("SQ", FileOrganization.SEQUENTIAL, PrimeKey(), True, 14),
                "PGMX",
            ),
            (
                FileFrame("IX", FileOrganization.INDEXED, PrimeKey(3, 4), False, 12),
                "PGMX",
            ),
            (
                FileFrame("RL", FileOrganization.RELATIVE, PrimeKey(), False, 6),
                "PGMX",
            ),
        ],
        [
            ("SQ", "INPUT", "PGMX"),
            ("IX", "INPUT", "PGMX"),
            ("RL", "INPUT", "PGMX"),
        ],
    )
