"""A READ of an indexed file passes the provider its key of reference's bytes when it
is a random READ, and no key when it is a sequential one."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.frontend import make_cobol_parser
from interpreter.instructions import CallFunction, Const, InstructionBase
from interpreter.project.cobol_compile import compile_cobol_module
from interpreter.register import Register
from tests.covers import covers

_READS = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PGMX.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT DX ASSIGN TO DXDD ORGANIZATION INDEXED
               ACCESS DYNAMIC RECORD KEY DX-ID.
           SELECT SX ASSIGN TO SXDD ORGANIZATION INDEXED
               ACCESS SEQUENTIAL RECORD KEY SX-ID.
       DATA DIVISION.
       FILE SECTION.
       FD  DX.
       01  DX-REC.
           05  DX-TAG PIC X.
           05  DX-ID  PIC X(4).
       FD  SX.
       01  SX-REC.
           05  SX-ID  PIC X(3).
       PROCEDURE DIVISION.
           READ DX.
           READ DX KEY IS DX-ID.
           READ DX NEXT.
           READ SX.
           GOBACK.
"""


def _read_keys(ir: tuple[InstructionBase, ...]) -> list[str]:
    produced = {
        **{i.result_reg: f"const {i.value!r}" for i in ir if isinstance(i, Const)},
        **{i.result_reg: str(i.func_name) for i in ir if isinstance(i, CallFunction)},
    }
    return [
        produced[Register(str(i.args[1]))]
        for i in ir
        if isinstance(i, CallFunction) and str(i.func_name) == "__cobol_read_record"
    ]


@covers(CobolFeature.READ)
def test_only_a_random_read_passes_its_key_bytes(tmp_path: Path) -> None:
    parser = make_cobol_parser()
    ast_path = tmp_path / "program.ast.json"
    parser.parse_to_file(_READS, ast_path)
    ir = compile_cobol_module(_READS, parser=parser, ast_path=ast_path).ir
    assert _read_keys(ir) == [
        "__bytes_to_string",
        "__bytes_to_string",
        "const ''",
        "const ''",
    ]
