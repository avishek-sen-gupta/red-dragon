"""Every COBOL file call the lowering emits names the calling program last."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.file_enums import FileOrganization
from interpreter.cobol.data_literals import text
from interpreter.cobol.file_definitions_data import FILE_DEFINITIONS
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.io_provider import IOResult, NullIOProvider
from interpreter.cobol.prime_key import PrimeKey
from interpreter.data_value import DataList, DataRecord, DataValue
from interpreter.field_name import FieldName
from interpreter.frontend import make_cobol_parser
from interpreter.instructions import CallFunction, Const, Data, InstructionBase
from interpreter.project.cobol_compile import compile_cobol_module
from interpreter.register import Register
from interpreter.run import run
from tests.covers import NotLanguageFeature, covers

_PGMX = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PGMX.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT F1 ASSIGN TO F1DD.
       DATA DIVISION.
       FILE SECTION.
       FD  F1.
       01  F1-REC PIC X(10).
       PROCEDURE DIVISION.
           OPEN INPUT F1.
           READ F1.
           CLOSE F1.
           GOBACK.
"""

_ALL_VERBS = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PGMX.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT KF ASSIGN TO KFDD ORGANIZATION INDEXED
               ACCESS DYNAMIC RECORD KEY KF-ID.
       DATA DIVISION.
       FILE SECTION.
       FD  KF.
       01  KF-REC.
           05  KF-ID   PIC X(4).
           05  KF-DATA PIC X(6).
       PROCEDURE DIVISION.
       DECLARATIVES.
       ON-IO SECTION.
           USE AFTER ERROR PROCEDURE ON I-O.
       ON-IO-EXIT.
           EXIT.
       END DECLARATIVES.
       MAIN SECTION.
       MAIN-PARA.
           OPEN I-O KF.
           WRITE KF-REC.
           READ KF.
           REWRITE KF-REC.
           START KF KEY IS EQUAL TO KF-ID.
           DELETE KF.
           CLOSE KF.
           GOBACK.
"""

_FILE_CALLS = frozenset(
    {
        "__cobol_declare_file",
        "__cobol_open_file",
        "__cobol_read_record",
        "__cobol_write_record",
        "__cobol_rewrite_record",
        "__cobol_start_file",
        "__cobol_delete_record",
        "__cobol_close_file",
        "__cobol_io_status",
        "__cobol_io_data",
        "__cobol_io_record_number",
    }
)


def _ir(source: bytes, tmp_path: Path) -> tuple[InstructionBase, ...]:
    parser = make_cobol_parser()
    ast_path = tmp_path / "program.ast.json"
    parser.parse_to_file(source, ast_path)
    return compile_cobol_module(source, parser=parser, ast_path=ast_path).ir


def _producers(
    ir: tuple[InstructionBase, ...],
) -> dict[Register, str | int | DataRecord]:
    consts: dict[Register, str | int | DataRecord] = {
        i.result_reg: i.value for i in ir if isinstance(i, Const)
    }
    calls: dict[Register, str | int | DataRecord] = {
        i.result_reg: f"<{i.func_name}>" for i in ir if isinstance(i, CallFunction)
    }
    return {**consts, **calls}


def _file_calls(
    ir: tuple[InstructionBase, ...],
) -> list[tuple[str, tuple[str | int | DataRecord, ...]]]:
    produced = _producers(ir)
    return [
        (str(i.func_name), tuple(produced[Register(str(a))] for a in i.args))
        for i in ir
        if isinstance(i, CallFunction) and str(i.func_name) in _FILE_CALLS
    ]


def _named(value: DataValue, name: str) -> DataValue:
    match value:
        case DataRecord(fields=fields):
            return next(f.value for f in fields if f.name == FieldName(name))
        case _:
            raise AssertionError(f"not a record: {value!r}")


def _items(value: DataValue) -> tuple[DataValue, ...]:
    match value:
        case DataList(items=items):
            return items
        case _:
            raise AssertionError(f"not a list: {value!r}")


class _Recording(NullIOProvider):
    """Records each provider method it is called through, with the program named."""

    def __init__(self) -> None:
        self.seen: tuple[tuple[str, str], ...] = ()

    def _saw(self, method: str, program: str) -> None:
        self.seen = (*self.seen, (method, program))

    def _declare_file(self, frame: DataRecord, program: str) -> IOResult:
        self._saw("declare_file", program)
        return IOResult("00", None)

    def _open_file(self, filename: str, mode: str, program: str) -> IOResult:
        self._saw("open_file", program)
        return IOResult("00", None)

    def _read_record(self, filename: str, key: str, program: str) -> IOResult:
        self._saw("read_record", program)
        return IOResult("00", "RECORD0001")

    def _close_file(self, filename: str, program: str) -> IOResult:
        self._saw("close_file", program)
        return IOResult("00", None)

    def _io_status(self, raw: IOResult, program: str) -> str:
        self._saw("io_status", program)
        return raw.status

    def _io_data(self, raw: IOResult, program: str) -> str:
        self._saw("io_data", program)
        return raw.data or ""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_file_call_names_the_calling_program_last(tmp_path):
    ir = _ir(_PGMX, tmp_path)
    (definitions,) = (
        i.value for i in ir if isinstance(i, Data) and i.name == FILE_DEFINITIONS
    )
    (f1,) = _items(_named(definitions, "files"))
    recording = _Recording()
    run(
        source=_PGMX.decode(),
        language="cobol",
        io_provider=recording,
        max_steps=1000,
    )
    assert (_file_calls(ir), recording.seen, _named(f1, "program")) == (
        [
            (
                "__cobol_declare_file",
                (
                    FileFrame(
                        "F1", FileOrganization.SEQUENTIAL, PrimeKey(), False, 10
                    ).data(),
                    "PGMX",
                ),
            ),
            ("__cobol_open_file", ("F1", "INPUT", "PGMX")),
            ("__cobol_io_status", ("<__cobol_open_file>", "PGMX")),
            ("__cobol_read_record", ("F1", "", "PGMX")),
            ("__cobol_io_status", ("<__cobol_read_record>", "PGMX")),
            ("__cobol_io_data", ("<__cobol_read_record>", "PGMX")),
            ("__cobol_io_record_number", ("<__cobol_read_record>", "PGMX")),
            ("__cobol_close_file", ("F1", "PGMX")),
            ("__cobol_io_status", ("<__cobol_close_file>", "PGMX")),
        ],
        (
            ("declare_file", "PGMX"),
            ("open_file", "PGMX"),
            ("io_status", "PGMX"),
            ("read_record", "PGMX"),
            ("io_status", "PGMX"),
            ("io_data", "PGMX"),
            ("close_file", "PGMX"),
            ("io_status", "PGMX"),
        ),
        text("PGMX"),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_kind_of_file_call_names_the_calling_program_last(tmp_path):
    calls = _file_calls(_ir(_ALL_VERBS, tmp_path))
    assert (
        {name for name, _args in calls},
        {args[-1] for _name, args in calls},
    ) == (set(_FILE_CALLS), {"PGMX"})
