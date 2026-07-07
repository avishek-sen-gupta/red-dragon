"""Integration tests for extract_cobol_connections().

Tests use inline COBOL source (extra_subprogram_sources) for CALL connections
and tmp_path fixture files for COPY connections (ProLeap resolves COPY on disk).

TestFixtureProject exercises the full on-disk pipeline against
tests/fixtures/projects/cobol_connections_demo/ — the durable e2e case.
"""

from pathlib import Path

import pytest

from tests.covers import covers, NotLanguageFeature
from interpreter.cobol.cobol_parser import make_cobol_parser
from interpreter.project.cobol_connections import extract_cobol_connections
from interpreter.project.graph_types import EdgeKind, NodeKind

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
        _nodes, edges = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
            parser=cobol_parser,
        )
        call_edges = [e for e in edges if e.kind == EdgeKind.CALL]
        assert len(call_edges) == 1
        assert call_edges[0].source == "MAIN"
        assert call_edges[0].target == "HELPER"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_target_file_path_resolved(self, cobol_parser):
        nodes, _edges = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
            parser=cobol_parser,
        )
        helper = next(
            n for n in nodes if n.kind == NodeKind.PROGRAM and n.id == "HELPER"
        )
        assert helper.file_path is not None
        assert Path(helper.file_path).stem.upper() == "HELPER"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_connections_for_standalone_program(self, cobol_parser):
        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. STANDALONE.
       PROCEDURE DIVISION.
           GOBACK.
"""
        nodes, edges = extract_cobol_connections(src, parser=cobol_parser)
        assert edges == []
        assert [n.id for n in nodes] == ["STANDALONE"]

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_returns_node_and_edge_lists(self, cobol_parser):
        nodes, edges = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
            parser=cobol_parser,
        )
        assert isinstance(nodes, list)
        assert isinstance(edges, list)
        assert all(n.kind is NodeKind.PROGRAM for n in nodes)
        assert all(e.kind is EdgeKind.CALL for e in edges)

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
        nodes, edges = extract_cobol_connections(
            prog_a,
            extra_subprogram_sources={"PROGB": prog_b, "PROGC": prog_c},
            parser=cobol_parser,
        )
        call_edges = [e for e in edges if e.kind == EdgeKind.CALL]
        pairs = {(e.source, e.target) for e in call_edges}
        assert ("PROGA", "PROGB") in pairs
        assert ("PROGB", "PROGC") in pairs
        # import_graph is flat: only main→direct-callees are resolved; B→C has no path
        progc = next(
            n for n in nodes if n.kind == NodeKind.PROGRAM and n.id == "PROGC"
        )
        assert progc.file_path is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_main_source_file_path_is_sentinel(self, cobol_parser):
        # compile_cobol() uses Path("__main__.cbl") as the main module path;
        # callers should not rely on file_path being a real filesystem path
        # when source is passed as bytes (no source_file argument).
        nodes, _edges = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
            parser=cobol_parser,
        )
        main = next(n for n in nodes if n.kind == NodeKind.PROGRAM and n.id == "MAIN")
        assert main.file_path == "__main__.cbl"


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
        _nodes, edges = extract_cobol_connections(
            (cbl / "MAIN.cbl").read_bytes(),
            copybook_dirs=[cpy],
            program_source_dirs=[cbl],
            parser=parser,
        )

        triples = [(e.kind.value, e.source, e.target) for e in edges]
        assert ("COPY", "MAIN", "CUSTREC") in triples
        assert ("CALL", "MAIN", "VALIDATE") in triples
        assert ("CALL", "MAIN", "RPTPROG") in triples
        assert ("COPY", "VALIDATE", "CUSTREC") in triples
        assert ("CALL", "VALIDATE", "LOGERR") in triples

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_fixture_call_file_paths_resolved(self):
        cbl = _FIXTURE / "cbl"
        cpy = _FIXTURE / "cpy"
        parser = make_cobol_parser(copybook_dirs=[cpy])
        nodes, _edges = extract_cobol_connections(
            (cbl / "MAIN.cbl").read_bytes(),
            copybook_dirs=[cpy],
            program_source_dirs=[cbl],
            parser=parser,
        )
        by_id = {n.id: n for n in nodes if n.kind == NodeKind.PROGRAM}
        assert by_id["VALIDATE"].file_path == str((cbl / "VALIDATE.cbl").resolve())
        assert by_id["RPTPROG"].file_path == str((cbl / "RPTPROG.cbl").resolve())

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_fixture_copy_target_file_path_is_none(self):
        cbl = _FIXTURE / "cbl"
        cpy = _FIXTURE / "cpy"
        parser = make_cobol_parser(copybook_dirs=[cpy])
        nodes, _edges = extract_cobol_connections(
            (cbl / "MAIN.cbl").read_bytes(),
            copybook_dirs=[cpy],
            program_source_dirs=[cbl],
            parser=parser,
        )
        copybook_nodes = [n for n in nodes if n.kind == NodeKind.COPYBOOK]
        assert copybook_nodes
        assert all(n.file_path is None for n in copybook_nodes)


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
        _nodes, edges = extract_cobol_connections(
            src, copybook_dirs=[tmp_path], parser=parser
        )
        copy_edges = [e for e in edges if e.kind == EdgeKind.COPY]
        assert len(copy_edges) == 1
        assert copy_edges[0].source == "MAINPROG"
        assert copy_edges[0].target == "MYREC"

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
        nodes, _edges = extract_cobol_connections(
            src, copybook_dirs=[tmp_path], parser=parser
        )
        myrec = next(
            n for n in nodes if n.kind == NodeKind.COPYBOOK and n.id == "MYREC"
        )
        assert myrec.file_path is None
