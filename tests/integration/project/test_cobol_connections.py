"""Integration tests for extract_cobol_connections().

Tests use inline COBOL source (extra_subprogram_sources) for CALL connections
and tmp_path fixture files for COPY connections (ProLeap resolves COPY on disk).
"""

from pathlib import Path

from tests.covers import covers, NotLanguageFeature
from interpreter.project.cobol_connections import Connection, extract_cobol_connections

_MAIN_CALL = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAIN.
       PROCEDURE DIVISION.
           CALL 'HELPER'.
           GOBACK.
"""

_HELPER = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELPER.
       PROCEDURE DIVISION.
           GOBACK.
"""


class TestCallConnections:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_connection_detected(self):
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        assert len(call_conns) == 1
        assert call_conns[0].source.name == "MAIN"
        assert call_conns[0].target.name == "HELPER"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_target_file_path_resolved(self):
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        assert call_conns[0].target.file_path is not None
        assert call_conns[0].target.file_path.stem.upper() == "HELPER"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_connections_for_standalone_program(self):
        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. STANDALONE.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(src)
        assert conns == []

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_returns_list_of_connection_objects(self):
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
        )
        assert isinstance(conns, list)
        assert all(isinstance(c, Connection) for c in conns)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_transitive_calls_included(self):
        """A calls B, B calls C — all three connections returned."""
        prog_a = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROGA.
       PROCEDURE DIVISION.
           CALL 'PROGB'.
           GOBACK.
"""
        prog_b = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROGB.
       PROCEDURE DIVISION.
           CALL 'PROGC'.
           GOBACK.
"""
        prog_c = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROGC.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(
            prog_a,
            extra_subprogram_sources={"PROGB": prog_b, "PROGC": prog_c},
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        names = {(c.source.name.upper(), c.target.name.upper()) for c in call_conns}
        assert ("PROGA", "PROGB") in names
        assert ("PROGB", "PROGC") in names


class TestCopyConnections:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_copy_connection_detected(self, tmp_path: Path):
        cpy_file = tmp_path / "MYREC.cpy"
        cpy_file.write_text("       01 MY-FIELD PIC X(10).\n")

        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           COPY MYREC.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(src, copybook_dirs=[tmp_path])
        copy_conns = [c for c in conns if c.kind == "COPY"]
        assert len(copy_conns) == 1
        assert copy_conns[0].source.name == "MAINPROG"
        assert copy_conns[0].target.name == "MYREC"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_copy_target_file_path_is_none(self, tmp_path: Path):
        cpy_file = tmp_path / "MYREC.cpy"
        cpy_file.write_text("       01 MY-FIELD PIC X(10).\n")

        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           COPY MYREC.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(src, copybook_dirs=[tmp_path])
        copy_conns = [c for c in conns if c.kind == "COPY"]
        assert copy_conns[0].target.file_path is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_to_json_roundtrips_for_copy(self, tmp_path: Path):
        import json

        cpy_file = tmp_path / "MYREC.cpy"
        cpy_file.write_text("       01 MY-FIELD PIC X(10).\n")

        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           COPY MYREC.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(src, copybook_dirs=[tmp_path])
        copy_conns = [c for c in conns if c.kind == "COPY"]
        data = json.loads(copy_conns[0].to_json())
        assert data["kind"] == "COPY"
        assert data["target_file"] is None
        assert data["target_name"] == "MYREC"
