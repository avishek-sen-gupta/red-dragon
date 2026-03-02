"""Tests for COBOL parser subprocess bridge."""

import json

from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.cobol_statements import DisplayStatement
from interpreter.cobol.subprocess_runner import CobolParseError, SubprocessRunner

import pytest


class FakeSubprocessRunner(SubprocessRunner):
    """Test double that returns canned JSON output."""

    def __init__(self, output: str, should_fail: bool = False):
        self._output = output
        self._should_fail = should_fail

    def run(self, command: list[str], input_data: str) -> str:
        if self._should_fail:
            raise CobolParseError("Fake parse error")
        return self._output


class TestProLeapCobolParser:
    def test_parse_minimal_asg(self):
        asg_dict = {
            "data_fields": [
                {"name": "WS-A", "level": 77, "pic": "9(5)", "offset": 0},
            ],
            "paragraphs": [
                {
                    "name": "MAIN",
                    "statements": [{"type": "STOP_RUN"}],
                },
            ],
        }
        runner = FakeSubprocessRunner(json.dumps(asg_dict))
        parser = ProLeapCobolParser(runner, "proleap-bridge.jar")

        asg = parser.parse(b"IDENTIFICATION DIVISION...")
        assert len(asg.data_fields) == 1
        assert asg.data_fields[0].name == "WS-A"
        assert len(asg.paragraphs) == 1
        assert asg.paragraphs[0].name == "MAIN"

    def test_parse_with_sections(self):
        asg_dict = {
            "data_fields": [],
            "sections": [
                {
                    "name": "MAIN-SECTION",
                    "paragraphs": [
                        {
                            "name": "INIT-PARA",
                            "statements": [
                                {"type": "DISPLAY", "operands": ["HELLO"]},
                            ],
                        },
                    ],
                },
            ],
        }
        runner = FakeSubprocessRunner(json.dumps(asg_dict))
        parser = ProLeapCobolParser(runner, "proleap-bridge.jar")

        asg = parser.parse(b"")
        assert len(asg.sections) == 1
        assert isinstance(asg.sections[0].paragraphs[0].statements[0], DisplayStatement)

    def test_parse_error_raises(self):
        runner = FakeSubprocessRunner("", should_fail=True)
        parser = ProLeapCobolParser(runner, "proleap-bridge.jar")

        with pytest.raises(CobolParseError):
            parser.parse(b"BAD SOURCE")

    def test_command_includes_jar_path(self):
        class CapturingRunner(SubprocessRunner):
            def __init__(self):
                self.captured_command: list[str] = []

            def run(self, command: list[str], input_data: str) -> str:
                self.captured_command = command
                return json.dumps({"data_fields": [], "paragraphs": []})

        runner = CapturingRunner()
        parser = ProLeapCobolParser(runner, "/path/to/bridge.jar")
        parser.parse(b"SOURCE")

        assert runner.captured_command == ["java", "-jar", "/path/to/bridge.jar"]

    def test_source_passed_as_stdin(self):
        class CapturingRunner(SubprocessRunner):
            def __init__(self):
                self.captured_input = ""

            def run(self, command: list[str], input_data: str) -> str:
                self.captured_input = input_data
                return json.dumps({"data_fields": []})

        runner = CapturingRunner()
        parser = ProLeapCobolParser(runner, "bridge.jar")
        parser.parse(b"IDENTIFICATION DIVISION.\nPROGRAM-ID. TEST.")

        assert runner.captured_input == "IDENTIFICATION DIVISION.\nPROGRAM-ID. TEST."
