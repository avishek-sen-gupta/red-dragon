"""Unit tests for ProLeapCobolParser copybook-dir handling."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from cobol_asg.cobol_parser import CobolParseError, ProLeapCobolParser
from cobol_asg.copybook_library import CopybookLibrary
from cobol_asg.copybook_search import CopybookSearch
from cobol_asg.lp64 import Lp64
from cobol_asg.subprocess_runner import SubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


class _RecordingRunner(SubprocessRunner):
    """Captures the command; returns a fixed minimal ASG JSON."""

    def __init__(
        self,
        stdout: str = '{"programs": [{"program_id": "T"}]}',
        failures: Sequence[Exception] = (),
    ):
        self.command: list[str] = []
        self.input_data = ""
        self._stdout = stdout
        self._failures = tuple(failures)

    def run(self, command: list[str], input_data: str) -> str:
        self.command = command
        self.input_data = input_data
        if self._failures:
            raise self._failures[0]
        return self._stdout


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_parse_appends_copybook_dir_args():
    runner = _RecordingRunner()
    parser = ProLeapCobolParser(
        runner,
        "bridge.jar",
        CopybookSearch(dirs=(Path("/a/cpy"), Path("/b/cpy-bms"))),
    )
    parser.parse(b"       PROGRAM-ID. T.\n")
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
    assert "-copybook-dir" not in runner.command


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_parse_accepts_source_bytes_that_are_not_utf8():
    """A fixed-format member is 8-bit text, not UTF-8. High bytes appear in real
    members (HIGH-VALUES sentinels, VALUE literals in report layouts) and used to
    raise UnicodeDecodeError before the source reached the bridge at all."""
    runner = _RecordingRunner()
    parser = ProLeapCobolParser(runner, "bridge.jar")
    parser.parse(b"       01 WS-SENTINEL PIC X VALUE '\xff'.\n")
    assert "\u00ff" in runner.input_data


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_parse_appends_copybook_ext_args():
    runner = _RecordingRunner()
    parser = ProLeapCobolParser(
        runner, "bridge.jar", CopybookSearch(exts=("txt", "CPY"))
    )
    parser.parse(b"       PROGRAM-ID. T.\n")
    idxs = [i for i, a in enumerate(runner.command) if a == "-copybook-ext"]
    assert len(idxs) == 2
    assert runner.command[idxs[0] + 1] == "txt"
    assert runner.command[idxs[1] + 1] == "CPY"


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_parse_no_exts_leaves_the_bridge_default_in_place():
    runner = _RecordingRunner()
    parser = ProLeapCobolParser(runner, "bridge.jar")
    parser.parse(b"       PROGRAM-ID. T.\n")
    assert "-copybook-ext" not in runner.command


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_each_copybook_library_reaches_the_bridge_as_its_name_and_directory():
    runner = _RecordingRunner()
    parser = ProLeapCobolParser(
        runner,
        "bridge.jar",
        CopybookSearch(
            libraries=(
                CopybookLibrary("LIB47", Path("/libs/one")),
                CopybookLibrary("LIB48", Path("/libs/two")),
            )
        ),
    ).with_addressing_mode(Lp64())
    parser.parse(b"       PROGRAM-ID. T.\n")
    assert runner.command == [
        "java",
        "-jar",
        "bridge.jar",
        "-copybook-library",
        "LIB47",
        "/libs/one",
        "-copybook-library",
        "LIB48",
        "/libs/two",
    ]


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_missing_copybook_raises_clean_error():
    raw = CobolParseError(
        "ProLeap bridge failed (exit 1): "
        "io.proleap.cobol.preprocessor.exception.CobolPreprocessorException: "
        "Could not find copy book MYBOOK in directory of COBOL input file"
    )
    runner = _RecordingRunner(failures=(raw,))
    parser = ProLeapCobolParser(
        runner, "bridge.jar", CopybookSearch(dirs=(Path("/x/cpy"),))
    )
    with pytest.raises(CobolParseError) as excinfo:
        parser.parse(b"       COPY MYBOOK.\n")
    text = str(excinfo.value)
    assert "MYBOOK" in text
    assert "/x/cpy" in text
    # Wrap-and-raise (red-dragon-vgm5): the underlying parser error is surfaced
    # verbatim — we no longer regex-scrape the copybook name out of it.
    assert "Could not find copy book" in text
    # And the original error is chained as the cause.
    assert excinfo.value.__cause__ is raw


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_non_copybook_error_passes_through():
    raw = CobolParseError("ProLeap bridge failed (exit 1): some other syntax error")
    runner = _RecordingRunner(failures=(raw,))
    parser = ProLeapCobolParser(runner, "bridge.jar")
    with pytest.raises(CobolParseError) as excinfo:
        parser.parse(b"       PROGRAM-ID. T.\n")
    assert "some other syntax error" in str(excinfo.value)


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_get_cobol_frontend_builds_a_proleap_backed_frontend():
    from interpreter.cobol.cobol_frontend import CobolFrontend
    from interpreter.frontends import get_cobol_frontend

    frontend = get_cobol_frontend(copybook_dirs=[Path("/proj/cpy")], tolerant=True)
    assert type(frontend) is CobolFrontend
    assert type(frontend._parser) is ProLeapCobolParser
    assert frontend._parser._copybooks == CopybookSearch(dirs=(Path("/proj/cpy"),))
    assert frontend._options.tolerant is True
