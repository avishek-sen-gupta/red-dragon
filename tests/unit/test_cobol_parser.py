"""Tests for COBOL parser subprocess bridge."""

import json
from pathlib import Path

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser, make_cobol_parser
from interpreter.cobol.subprocess_runner import CobolParseError
from interpreter.cobol.features import CobolFeature
from tests.covers import NotLanguageFeature, covers

_MINIMAL = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTPROG.
       PROCEDURE DIVISION.
           GOBACK.
"""

_WITH_DATA = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       77 WS-A PIC 9(5).
       PROCEDURE DIVISION.
           GOBACK.
"""

_WITH_SECTION = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       77 WS-A PIC 9(5).
       PROCEDURE DIVISION.
       MAIN-SECTION SECTION.
       INIT-PARA.
           DISPLAY 'HELLO'.
           GOBACK.
"""


class TestProLeapCobolParser:
    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_parse_minimal_asg(self):
        parser = make_cobol_parser()
        asg = parser.parse(_MINIMAL)
        assert asg is not None

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_parse_data_field(self):
        parser = make_cobol_parser()
        asg = parser.parse(_WITH_DATA)
        assert len(asg.data_fields) == 1
        assert asg.data_fields[0].name == "WS-A"

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_parse_with_sections(self):
        parser = make_cobol_parser()
        asg = parser.parse(_WITH_SECTION)
        assert len(asg.sections) == 1
        assert asg.sections[0].name == "MAIN-SECTION"

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_parse_error_raises(self):
        parser = make_cobol_parser()
        with pytest.raises(CobolParseError):
            parser.parse(b"THIS IS NOT VALID COBOL AT ALL {{{{")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_to_file_writes_valid_json(tmp_path):
    out = tmp_path / "prog.ast.json"
    parser = make_cobol_parser()
    result = parser.parse_to_file(_MINIMAL, out)
    assert result == out
    assert out.exists()
    data = json.loads(out.read_text())
    assert (
        "paragraphs" in data
        or "sections" in data
        or "data_fields" in data
        or "statements" in data
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_to_file_returns_path_not_string(tmp_path):
    out = tmp_path / "prog.ast.json"
    parser = make_cobol_parser()
    result = parser.parse_to_file(_MINIMAL, out)
    assert isinstance(result, Path)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_make_cobol_parser_returns_proleap_parser():
    parser = make_cobol_parser()
    assert isinstance(parser, ProLeapCobolParser)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_make_cobol_parser_with_copybook_dirs_passes_them_through(tmp_path):
    parser = make_cobol_parser(copybook_dirs=[tmp_path])
    assert isinstance(parser, ProLeapCobolParser)
