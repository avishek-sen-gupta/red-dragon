"""Unit tests for Connection data model."""

import json
from pathlib import Path

from tests.covers import covers, NotLanguageFeature
from interpreter.project.cobol_connections import Connection, ProgramRef


class TestProgramRef:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_program_ref_stores_name_and_path(self):
        ref = ProgramRef(name="ACCTMGR", file_path=Path("/src/ACCTMGR.cbl"))
        assert ref.name == "ACCTMGR"
        assert ref.file_path == Path("/src/ACCTMGR.cbl")

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_program_ref_file_path_may_be_none(self):
        ref = ProgramRef(name="DFHEIBLK", file_path=None)
        assert ref.file_path is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_program_ref_is_hashable(self):
        ref = ProgramRef(name="PROG", file_path=None)
        assert hash(ref) is not None
        assert {ref}  # can be used in a set


class TestConnection:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_connection_stores_kind_source_target(self):
        src = ProgramRef(name="MAIN", file_path=Path("/src/MAIN.cbl"))
        tgt = ProgramRef(name="SUB", file_path=Path("/src/SUB.cbl"))
        conn = Connection(kind="CALL", source=src, target=tgt)
        assert conn.kind == "CALL"
        assert conn.source is src
        assert conn.target is tgt

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_to_json_includes_all_fields(self):
        src = ProgramRef(name="MAIN", file_path=Path("/src/MAIN.cbl"))
        tgt = ProgramRef(name="SUB", file_path=Path("/src/SUB.cbl"))
        conn = Connection(kind="CALL", source=src, target=tgt)
        data = json.loads(conn.to_json())
        assert data["kind"] == "CALL"
        assert data["source_name"] == "MAIN"
        assert data["source_file"] == "/src/MAIN.cbl"
        assert data["target_name"] == "SUB"
        assert data["target_file"] == "/src/SUB.cbl"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_copy_to_json_has_null_target_file(self):
        src = ProgramRef(name="MAIN", file_path=Path("/src/MAIN.cbl"))
        tgt = ProgramRef(name="DFHEIBLK", file_path=None)
        conn = Connection(kind="COPY", source=src, target=tgt)
        data = json.loads(conn.to_json())
        assert data["kind"] == "COPY"
        assert data["target_file"] is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_connection_is_hashable(self):
        src = ProgramRef(name="MAIN", file_path=None)
        tgt = ProgramRef(name="SUB", file_path=None)
        conn = Connection(kind="CALL", source=src, target=tgt)
        assert {conn}
