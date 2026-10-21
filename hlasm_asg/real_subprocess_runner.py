# pyright: standard
"""Runs a command with subprocess, the imperative shell of the bridge parser."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Sequence

from hlasm_asg.process_result import ProcessResult
from hlasm_asg.subprocess_runner import SubprocessRunner

logger = logging.getLogger(__name__)


class RealSubprocessRunner(SubprocessRunner):
    def run(self, command: Sequence[str]) -> ProcessResult:
        logger.debug("Running subprocess: %s", " ".join(command))
        completed = subprocess.run(
            command, capture_output=True, encoding="utf-8", check=False
        )
        return ProcessResult(completed.returncode, completed.stdout, completed.stderr)
