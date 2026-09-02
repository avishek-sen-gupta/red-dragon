"""Subprocess execution abstraction for dependency injection.

Provides a seam for testing: production code uses RealSubprocessRunner,
tests inject FakeSubprocessRunner with canned output.
"""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Sequence

logger = logging.getLogger(__name__)


class SubprocessRunner(ABC):
    """Abstract subprocess execution interface."""

    @abstractmethod
    def run(self, command: Sequence[str], input_data: str) -> str:
        """Execute a command with stdin input and return stdout."""
        ...


class RealSubprocessRunner(SubprocessRunner):
    """Production subprocess runner using subprocess.run."""

    def run(self, command: Sequence[str], input_data: str) -> str:
        logger.debug("Running subprocess: %s", " ".join(command))
        result = subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            # latin-1 both ways, matching `decode_source` and the bridge's own
            # SOURCE_CHARSET: this is the byte-identity codec, so a member's high
            # bytes reach the parser unchanged and come back out of the JSON
            # unchanged. `text=True` would use the locale encoding instead, which
            # only round-trips by coincidence when that happens to be UTF-8 on
            # both sides -- and it stopped being one when the bridge started
            # reading its input as ISO-8859-1.
            encoding="latin-1",
            check=False,
        )
        if result.returncode != 0:
            raise CobolParseError(
                f"ProLeap bridge failed (exit {result.returncode}): {result.stderr}"
            )
        return result.stdout


class CobolParseError(Exception):
    """Raised when the ProLeap bridge fails to parse COBOL source."""
