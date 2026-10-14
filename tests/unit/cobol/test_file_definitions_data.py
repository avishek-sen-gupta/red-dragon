"""Lowering declares each SELECT and its FD format as the file-definitions Data."""

from __future__ import annotations

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.file_definitions_data import (
    FILE_DEFINITIONS,
    file_definitions_data,
)
from interpreter.constants import FoundationTypeName
from interpreter.data_value import DataField, DataList, DataRecord, DataScalar
from interpreter.field_name import FieldName
from interpreter.instructions import Data
from interpreter.types.type_expr import scalar
from tests.covers import FeatureStatus, NotLanguageFeature, covers

_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FILEDEFS.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-FILE ASSIGN TO INDD FILE STATUS IS WS-ST.
           SELECT KS-FILE ASSIGN TO KSDD ORGANIZATION INDEXED
               ACCESS DYNAMIC RECORD KEY KS-ID.
           SELECT NOFD-FILE ASSIGN TO NFDD.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-FILE RECORDING MODE V
           RECORD VARYING 10 TO 80 DEPENDING ON WS-LEN.
       01  IN-REC PIC X(80).
       01  IN-SHORT.
           05  IN-HEAD PIC X(8).
           05  IN-ITEM PIC X(4) OCCURS 1 TO 8 TIMES DEPENDING ON WS-N.
       FD  KS-FILE.
       01  KS-REC.
           05  KS-ID   PIC X(10).
           05  KS-DATA PIC X(40).
       WORKING-STORAGE SECTION.
       01  WS-ST  PIC XX.
       01  WS-LEN PIC 9(4) COMP.
       01  WS-N   PIC 9(2).
       PROCEDURE DIVISION.
           STOP RUN.
"""


def _text(value: str) -> DataScalar:
    return DataScalar(value, scalar(FoundationTypeName.STRING))


def _int(value: int) -> DataScalar:
    return DataScalar(value, scalar(FoundationTypeName.INT))


def _bool(value: bool) -> DataScalar:
    return DataScalar(value, scalar(FoundationTypeName.BOOL))


def _field(name: str, value: DataScalar | DataRecord | DataList) -> DataField:
    return DataField(FieldName(name), value)


@covers(CobolFeature.SECTION_FILE, status=FeatureStatus.PARTIAL)
def test_each_select_is_declared_with_its_fd_format():
    asg = make_cobol_parser().parse(_SOURCE)
    in_fd = DataRecord(
        (
            _field("recording_mode", _text("V")),
            _field(
                "record_clause",
                DataRecord(
                    (
                        _field("kind", _text("varying")),
                        _field("minimum", _int(10)),
                        _field("maximum", _int(80)),
                        _field("depending_on", _text("WS-LEN")),
                    )
                ),
            ),
            _field("record_lengths", DataList((_int(80), _int(40)))),
            _field("depending", _bool(True)),
        )
    )
    ks_fd = DataRecord(
        (
            _field("recording_mode", _text("")),
            _field("record_clause", DataRecord((_field("kind", _text("none")),))),
            _field("record_lengths", DataList((_int(50),))),
            _field("depending", _bool(False)),
        )
    )
    expected_files = DataList(
        (
            DataRecord(
                (
                    _field("file_name", _text("IN-FILE")),
                    _field("assign_to", _text("INDD")),
                    _field("organization", _text("SEQUENTIAL")),
                    _field("access_mode", _text("SEQUENTIAL")),
                    _field("record_key", _text("")),
                    _field("relative_key", _text("")),
                    _field("file_status", _text("WS-ST")),
                    _field("fd", DataList((in_fd,))),
                )
            ),
            DataRecord(
                (
                    _field("file_name", _text("KS-FILE")),
                    _field("assign_to", _text("KSDD")),
                    _field("organization", _text("INDEXED")),
                    _field("access_mode", _text("DYNAMIC")),
                    _field("record_key", _text("KS-ID")),
                    _field("relative_key", _text("")),
                    _field("file_status", _text("")),
                    _field("fd", DataList((ks_fd,))),
                )
            ),
            DataRecord(
                (
                    _field("file_name", _text("NOFD-FILE")),
                    _field("assign_to", _text("NFDD")),
                    _field("organization", _text("SEQUENTIAL")),
                    _field("access_mode", _text("SEQUENTIAL")),
                    _field("record_key", _text("")),
                    _field("relative_key", _text("")),
                    _field("file_status", _text("")),
                    _field("fd", DataList(())),
                )
            ),
        )
    )
    assert file_definitions_data(asg) == Data(
        name=FILE_DEFINITIONS, value=DataRecord((_field("files", expected_files),))
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_program_without_file_control_declares_no_files():
    assert file_definitions_data(CobolASG(program_id="BARE")) == Data(
        name=FILE_DEFINITIONS, value=DataRecord((_field("files", DataList(())),))
    )
