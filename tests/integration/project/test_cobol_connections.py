"""Integration tests for extract_cobol_connections().

Tests use inline COBOL source (extra_subprogram_sources) for CALL connections
and tmp_path fixture files for COPY connections (ProLeap resolves COPY on disk).

TestFixtureProject exercises the full on-disk pipeline against
tests/fixtures/projects/cobol_connections_demo/ — the durable e2e case.
"""

import json
from pathlib import Path

import pytest

from tests.covers import covers, NotLanguageFeature
from interpreter.cobol.cobol_parser import make_cobol_parser
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


@pytest.fixture
def cobol_parser():
    """Fixture providing a COBOL parser for all tests."""
    return make_cobol_parser()


class TestCallConnections:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_connection_detected(self, cobol_parser):
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
            parser=cobol_parser,
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        assert len(call_conns) == 1
        assert call_conns[0].source.name == "MAIN"
        assert call_conns[0].target.name == "HELPER"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_target_file_path_resolved(self, cobol_parser):
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
            parser=cobol_parser,
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        assert call_conns[0].target.file_path is not None
        assert call_conns[0].target.file_path.stem.upper() == "HELPER"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_connections_for_standalone_program(self, cobol_parser):
        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. STANDALONE.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(src, parser=cobol_parser)
        assert conns == []

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_returns_list_of_connection_objects(self, cobol_parser):
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
            parser=cobol_parser,
        )
        assert isinstance(conns, list)
        assert all(isinstance(c, Connection) for c in conns)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_transitive_calls_included(self, cobol_parser):
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
            parser=cobol_parser,
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        names = {(c.source.name.upper(), c.target.name.upper()) for c in call_conns}
        assert ("PROGA", "PROGB") in names
        assert ("PROGB", "PROGC") in names
        # import_graph is flat: only main→direct-callees are resolved; B→C has no path
        b_to_c = next(c for c in call_conns if c.source.name.upper() == "PROGB")
        assert (
            b_to_c.target.file_path is None
        )  # flat import_graph — indirect callee path not resolved

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_main_source_file_path_is_sentinel(self, cobol_parser):
        # compile_cobol() uses Path("__main__.cbl") as the main module path;
        # callers should not rely on source.file_path being a real filesystem path
        # when source is passed as bytes (no source_file argument).
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
            parser=cobol_parser,
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        assert call_conns[0].source.file_path == Path("__main__.cbl")


_FIXTURE = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "projects"
    / "cobol_connections_demo"
)


class TestFixtureProject:
    """E2E test using on-disk fixture: tests/fixtures/projects/cobol_connections_demo/"""

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_fixture_produces_expected_connections(self):
        cbl = _FIXTURE / "cbl"
        cpy = _FIXTURE / "cpy"
        parser = make_cobol_parser(copybook_dirs=[cpy])
        conns = extract_cobol_connections(
            (cbl / "MAIN.cbl").read_bytes(),
            copybook_dirs=[cpy],
            program_source_dirs=[cbl],
            parser=parser,
        )

        kinds = [(c.kind, c.source.name, c.target.name) for c in conns]
        assert ("COPY", "MAIN", "CUSTREC") in kinds
        assert ("CALL", "MAIN", "VALIDATE") in kinds
        assert ("CALL", "MAIN", "RPTPROG") in kinds
        assert ("COPY", "VALIDATE", "CUSTREC") in kinds
        assert ("CALL", "VALIDATE", "LOGERR") in kinds

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_fixture_call_file_paths_resolved(self):
        cbl = _FIXTURE / "cbl"
        cpy = _FIXTURE / "cpy"
        parser = make_cobol_parser(copybook_dirs=[cpy])
        conns = extract_cobol_connections(
            (cbl / "MAIN.cbl").read_bytes(),
            copybook_dirs=[cpy],
            program_source_dirs=[cbl],
            parser=parser,
        )
        call_conns = {c.target.name: c for c in conns if c.kind == "CALL"}
        assert (
            call_conns["VALIDATE"].target.file_path == (cbl / "VALIDATE.cbl").resolve()
        )
        assert call_conns["RPTPROG"].target.file_path == (cbl / "RPTPROG.cbl").resolve()

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_fixture_copy_target_file_path_is_none(self):
        cbl = _FIXTURE / "cbl"
        cpy = _FIXTURE / "cpy"
        parser = make_cobol_parser(copybook_dirs=[cpy])
        conns = extract_cobol_connections(
            (cbl / "MAIN.cbl").read_bytes(),
            copybook_dirs=[cpy],
            program_source_dirs=[cbl],
            parser=parser,
        )
        copy_conns = [c for c in conns if c.kind == "COPY"]
        assert all(c.target.file_path is None for c in copy_conns)


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
        parser = make_cobol_parser(copybook_dirs=[tmp_path])
        conns = extract_cobol_connections(src, copybook_dirs=[tmp_path], parser=parser)
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
        parser = make_cobol_parser(copybook_dirs=[tmp_path])
        conns = extract_cobol_connections(src, copybook_dirs=[tmp_path], parser=parser)
        copy_conns = [c for c in conns if c.kind == "COPY"]
        assert copy_conns[0].target.file_path is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_to_json_roundtrips_for_copy(self, tmp_path: Path):
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
        parser = make_cobol_parser(copybook_dirs=[tmp_path])
        conns = extract_cobol_connections(src, copybook_dirs=[tmp_path], parser=parser)
        copy_conns = [c for c in conns if c.kind == "COPY"]
        data = json.loads(copy_conns[0].to_json())
        assert data["kind"] == "COPY"
        assert data["target_file"] is None
        assert data["target_name"] == "MYREC"
