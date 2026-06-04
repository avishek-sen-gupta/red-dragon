"""Unit tests for ProLeapCobolParser copybook-dir handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser, CobolParseError
from interpreter.cobol.subprocess_runner import SubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


class _RecordingRunner(SubprocessRunner):
    """Captures the command; returns a fixed minimal ASG JSON."""

    def __init__(
        self, stdout: str = '{"program_id": "T"}', raise_exc: Exception | None = None
    ):
        self.command: list[str] | None = None
        self.input_data: str | None = None
        self._stdout = stdout
        self._raise = raise_exc

    def run(self, command: list[str], input_data: str) -> str:
        self.command = command
        self.input_data = input_data
        if self._raise is not None:
            raise self._raise
        return self._stdout


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_parse_appends_copybook_dir_args():
    runner = _RecordingRunner()
    parser = ProLeapCobolParser(
        runner, "bridge.jar", copybook_dirs=[Path("/a/cpy"), Path("/b/cpy-bms")]
    )
    parser.parse(b"       PROGRAM-ID. T.\n")
    assert runner.command is not None
    assert "-copybook-dir" in runner.command
    idxs = [i for i, a in enumerate(runner.command) if a == "-copybook-dir"]
    assert len(idxs) == 2
    assert runner.command[idxs[0] + 1] == "/a/cpy"
    assert runner.command[idxs[1] + 1] == "/b/cpy-bms"


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_parse_no_dirs_emits_no_copybook_dir_args():
    runner = _RecordingRunner()
    parser = ProLeapCobolParser(runner, "bridge.jar")
    parser.parse(b"       PROGRAM-ID. T.\n")
    assert runner.command is not None
    assert "-copybook-dir" not in runner.command
