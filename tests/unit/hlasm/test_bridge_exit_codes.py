# pyright: standard
"""The bridge parser tells assembly errors (exit 2) from bridge failures (any other non-zero exit)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from hlasm_asg.hlasm_bridge_failure import HlasmBridgeFailure
from hlasm_asg.hlasm_bridge_parser import HlasmBridgeParser
from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.process_result import ProcessResult
from hlasm_asg.program.diagnostic import Diagnostic
from hlasm_asg.program.severity import Severity
from hlasm_asg.subprocess_runner import SubprocessRunner
from tests.covers import NotLanguageFeature, covers

REFUSAL = (
    '{"diagnostics":[{"code":"E049","file":"src/a.asm","line":3,'
    '"message":"Operation code not found - X","related":[],"severity":"ERROR"}]}'
)


class ScriptedRunner(SubprocessRunner):
    def __init__(self, result: ProcessResult):
        self.result = result

    def run(self, command: Sequence[str]) -> ProcessResult:
        return self.result


class TestBridgeExitCodes:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_exit_two_is_a_parse_error_and_other_codes_are_bridge_failures(
        self, tmp_path: Path
    ):
        refused = ScriptedRunner(ProcessResult(2, "", REFUSAL))
        crashed = ScriptedRunner(ProcessResult(139, "", "segmentation fault"))
        out = tmp_path / "out.json"

        with pytest.raises(HlasmParseError, match="E049 line 3") as parse_error:
            HlasmBridgeParser(refused, "bridge").parse_to_file(b"X\n", "src/a.asm", out)
        with pytest.raises(HlasmBridgeFailure, match="exited 139") as failure:
            HlasmBridgeParser(crashed, "bridge").parse_to_file(b"X\n", "src/a.asm", out)

        assert parse_error.value.diagnostics == (
            Diagnostic(
                code="E049",
                severity=Severity.ERROR,
                message="Operation code not found - X",
                file="src/a.asm",
                line=3,
                related=(),
            ),
        )
        assert (failure.value.returncode, failure.value.stderr) == (
            139,
            "segmentation fault",
        )
        assert not out.exists()
