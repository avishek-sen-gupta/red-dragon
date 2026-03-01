"""Subprocess execution abstraction for dependency injection.

Provides a seam for testing: production code uses RealSubprocessRunner,
tests inject FakeSubprocessRunner with canned output.
"""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SubprocessRunner(ABC):
    """Abstract subprocess execution interface."""

    @abstractmethod
    def run(self, command: list[str], input_data: str) -> str:
        """Execute a command with stdin input and return stdout."""
        ...


class RealSubprocessRunner(SubprocessRunner):
    """Production subprocess runner using subprocess.run."""

    def run(self, command: list[str], input_data: str) -> str:
        logger.info("Running subprocess: %s", " ".join(command))
        result = subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise CobolParseError(
                f"ProLeap bridge failed (exit {result.returncode}): {result.stderr}"
            )
        return result.stdout


class CobolParseError(Exception):
    """Raised when the ProLeap bridge fails to parse COBOL source."""
