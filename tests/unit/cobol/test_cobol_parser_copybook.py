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


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_missing_copybook_raises_clean_error():
    raw = CobolParseError(
        "ProLeap bridge failed (exit 1): "
        "io.proleap.cobol.preprocessor.exception.CobolPreprocessorException: "
        "Could not find copy book MYBOOK in directory of COBOL input file"
    )
    runner = _RecordingRunner(raise_exc=raw)
    parser = ProLeapCobolParser(runner, "bridge.jar", copybook_dirs=[Path("/x/cpy")])
    with pytest.raises(CobolParseError) as excinfo:
        parser.parse(b"       COPY MYBOOK.\n")
    text = str(excinfo.value)
    assert "MYBOOK" in text
    assert "/x/cpy" in text
    assert "Could not find copy book" not in text  # raw Java message not leaked


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_non_copybook_error_passes_through():
    raw = CobolParseError("ProLeap bridge failed (exit 1): some other syntax error")
    runner = _RecordingRunner(raise_exc=raw)
    parser = ProLeapCobolParser(runner, "bridge.jar")
    with pytest.raises(CobolParseError) as excinfo:
        parser.parse(b"       PROGRAM-ID. T.\n")
    assert "some other syntax error" in str(excinfo.value)


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_get_frontend_passes_copybook_dirs(monkeypatch):
    import interpreter.frontend as frontend_mod
    from interpreter import constants
    from interpreter.constants import Language

    captured = {}

    class _SpyParser:
        def __init__(self, runner, bridge_jar, copybook_dirs=None):
            captured["copybook_dirs"] = copybook_dirs

    # get_frontend imports ProLeapCobolParser locally at call time, so patching
    # the module attribute is picked up.
    import interpreter.cobol.cobol_parser as cp

    monkeypatch.setattr(cp, "ProLeapCobolParser", _SpyParser)

    # COBOL only routes to ProLeapCobolParser via the FRONTEND_COBOL branch
    # (run.py resolves Language.COBOL -> FRONTEND_COBOL). The deterministic
    # default has no COBOL frontend, so the COBOL frontend_type is required.
    frontend_mod.get_frontend(
        Language.COBOL,
        frontend_type=constants.FRONTEND_COBOL,
        copybook_dirs=[Path("/proj/cpy")],
    )
    assert captured["copybook_dirs"] == [Path("/proj/cpy")]


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_collect_project_copybook_dirs(tmp_path):
    from interpreter.project.compiler import _collect_copybook_dirs

    root = tmp_path.resolve()
    (root / "cbl").mkdir()
    (root / "cpy").mkdir()
    (root / "cpy-bms").mkdir()
    dirs = _collect_copybook_dirs(root)
    assert root in dirs
    assert root / "cpy" in dirs
    assert root / "cpy-bms" in dirs
    assert root / "cbl" in dirs
