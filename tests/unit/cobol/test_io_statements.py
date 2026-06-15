# pyright: standard
"""Tests for COBOL I/O statement dataclasses and FileControlEntry."""

import pytest
from tests.covers import covers, NotLanguageFeature
from interpreter.cobol.cobol_statements import (
    FileControlEntry,
    OpenStatement,
    ReadStatement,
    WriteStatement,
    RewriteStatement,
    StartStatement,
    DeleteStatement,
)
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.file_enums import OpenMode, FileOrganization, AccessMode


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_control_entry_defaults():
    e = FileControlEntry(file_name="CUST-FILE")
    assert e.file_name == "CUST-FILE"
    assert e.assign_to == ""
    assert e.organization == FileOrganization.SEQUENTIAL
    assert e.access_mode == AccessMode.SEQUENTIAL
    assert e.record_key == ""
    assert e.relative_key == ""
    assert e.file_status_var == ""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_control_entry_from_dict():
    d = {
        "file_name": "CUST-FILE",
        "assign_to": "custfile.dat",
        "organization": "INDEXED",
        "access_mode": "DYNAMIC",
        "record_key": "CUST-ID",
        "relative_key": "",
        "file_status_var": "WS-STATUS",
    }
    e = FileControlEntry.from_dict(d)
    assert e.organization == FileOrganization.INDEXED
    assert e.access_mode == AccessMode.DYNAMIC
    assert e.record_key == "CUST-ID"
    assert e.file_status_var == "WS-STATUS"


@covers(CobolFeature.OPEN)
def test_open_statement_mode_groups_from_dict():
    d = {
        "type": "OPEN",
        "mode_groups": [
            {"mode": "INPUT", "files": ["CUST-FILE"]},
            {"mode": "OUTPUT", "files": ["REPORT-FILE"]},
        ],
    }
    stmt = OpenStatement.from_dict(d)
    assert len(stmt.mode_groups) == 2
    assert stmt.mode_groups[0] == (OpenMode.INPUT, ["CUST-FILE"])
    assert stmt.mode_groups[1] == (OpenMode.OUTPUT, ["REPORT-FILE"])


@covers(CobolFeature.OPEN)
def test_open_statement_to_dict_roundtrip():
    d = {"type": "OPEN", "mode_groups": [{"mode": "INPUT", "files": ["F1"]}]}
    assert OpenStatement.from_dict(d).to_dict() == d


@covers(CobolFeature.READ_AT_END)
def test_read_statement_conditional_fields():
    d = {
        "type": "READ",
        "file_name": "CUST-FILE",
        "key": "CUST-ID",
        "at_end": [{"type": "CONTINUE"}],
        "not_at_end": [],
        "invalid_key": [],
        "not_invalid_key": [],
    }
    stmt = ReadStatement.from_dict(d)
    assert stmt.key == "CUST-ID"
    assert len(stmt.at_end) == 1
    assert stmt.not_at_end == []


@covers(CobolFeature.WRITE)
def test_write_statement_invalid_key():
    d = {
        "type": "WRITE",
        "record_name": "CUST-REC",
        "invalid_key": [{"type": "CONTINUE"}],
        "not_invalid_key": [],
    }
    stmt = WriteStatement.from_dict(d)
    assert len(stmt.invalid_key) == 1
    assert stmt.not_invalid_key == []


@covers(CobolFeature.DELETE_RECORD)
def test_delete_statement_invalid_key():
    d = {
        "type": "DELETE",
        "file_name": "CUST-FILE",
        "invalid_key": [],
        "not_invalid_key": [{"type": "CONTINUE"}],
    }
    stmt = DeleteStatement.from_dict(d)
    assert len(stmt.not_invalid_key) == 1


@covers(CobolFeature.REWRITE)
def test_rewrite_statement_invalid_key():
    d = {
        "type": "REWRITE",
        "record_name": "CUST-REC",
        "invalid_key": [{"type": "CONTINUE"}],
        "not_invalid_key": [],
    }
    stmt = RewriteStatement.from_dict(d)
    assert len(stmt.invalid_key) == 1


@covers(CobolFeature.START)
def test_start_statement_relop_and_invalid_key():
    d = {
        "type": "START",
        "file_name": "CUST-FILE",
        "key": "CUST-ID",
        "relop": ">=",
        "invalid_key": [],
        "not_invalid_key": [],
    }
    stmt = StartStatement.from_dict(d)
    assert stmt.relop == ">="
    assert stmt.key == "CUST-ID"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_asg_file_control():
    from interpreter.cobol.asg_types import CobolASG

    asg = CobolASG.from_dict(
        {
            "file_control": [
                {
                    "file_name": "F1",
                    "assign_to": "f1.dat",
                    "organization": "SEQUENTIAL",
                    "access_mode": "SEQUENTIAL",
                    "record_key": "",
                    "relative_key": "",
                    "file_status_var": "",
                }
            ]
        }
    )
    assert len(asg.file_control) == 1
    assert asg.file_control[0].file_name == "F1"
