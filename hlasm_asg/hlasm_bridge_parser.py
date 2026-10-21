# pyright: standard
"""HLASM parser that delegates to the che4z hlasm_ast_bridge executable."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from hlasm_asg.diagnostic_report import DiagnosticReport
from hlasm_asg.hlasm_ast_parser import HlasmAstParser
from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.real_subprocess_runner import RealSubprocessRunner
from hlasm_asg.subprocess_runner import SubprocessRunner

logger = logging.getLogger(__name__)

SOURCE_FILE_NAME = "source.asm"
DEFAULT_BRIDGE = "hlasm-bridge/che4z/build/bin/hlasm_ast_bridge"
BRIDGE_ENV_VAR = "HLASM_AST_BRIDGE"
REFUSED_EXIT_CODE = 2


class HlasmBridgeParser(HlasmAstParser):
    def __init__(
        self, runner: SubprocessRunner, bridge: str, syslib: Sequence[Path] = ()
    ):
        self._runner = runner
        self._bridge = bridge
        self._syslib = tuple(syslib)

    def _command(self, source_path: Path) -> list[str]:
        libraries = [arg for d in self._syslib for arg in ("--syslib", str(d))]
        return [self._bridge, str(source_path), *libraries]

    def _run(self, source: bytes) -> str:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / SOURCE_FILE_NAME
            source_path.write_bytes(source)
            logger.debug(
                "Assembling %d bytes of HLASM via %s", len(source), self._bridge
            )
            result = self._runner.run(self._command(source_path))
        if result.returncode == 0:
            return result.stdout
        raise HlasmParseError(
            DiagnosticReport.model_validate_json(result.stderr).diagnostics
        )

    def parse_to_file(self, source: bytes, out_path: Path) -> Path:
        out_path.write_text(self._run(source), encoding="utf-8")
        return out_path

    def read(self, path: Path) -> HlasmProgram:
        return HlasmProgram.model_validate_json(path.read_text(encoding="utf-8"))


def make_hlasm_parser(syslib: Sequence[Path] = ()) -> HlasmBridgeParser:
    return HlasmBridgeParser(
        RealSubprocessRunner(),
        os.environ.get(BRIDGE_ENV_VAR, DEFAULT_BRIDGE),
        syslib,
    )
