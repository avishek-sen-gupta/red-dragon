# pyright: standard
"""COBOL parser — subprocess bridge to ProLeap.

The ProLeap bridge is a separate Java repo that parses COBOL source
using ANTLR4 and emits JSON ASG to stdout. This module wraps the
subprocess call and deserializes the JSON into CobolASG.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.subprocess_runner import SubprocessRunner, CobolParseError

logger = logging.getLogger(__name__)


class CobolParser(ABC):
    """Abstract COBOL parser interface."""

    @abstractmethod
    def parse(self, source: bytes) -> CobolASG:
        """Parse COBOL source bytes into an ASG."""
        ...


class ProLeapCobolParser(CobolParser):
    """COBOL parser that delegates to the ProLeap bridge via subprocess."""

    def __init__(
        self,
        runner: SubprocessRunner,
        bridge_jar: str,
        copybook_dirs: list[Path] | None = None,
    ):
        self._runner = runner
        self._bridge_jar = bridge_jar
        self._copybook_dirs: list[Path] = list(copybook_dirs or [])

    def parse(self, source: bytes) -> CobolASG:
        logger.info("Parsing COBOL source (%d bytes) via ProLeap bridge", len(source))
        command = ["java", "-jar", self._bridge_jar]
        for d in self._copybook_dirs:
            command += ["-copybook-dir", str(d)]
        try:
            json_str = self._runner.run(command, source.decode("utf-8"))
        except CobolParseError as e:
            raise self._enrich_copybook_error(e) from e
        data = json.loads(json_str)
        asg = CobolASG.from_dict(data)
        logger.info(
            "Parsed ASG: %d data fields, %d sections, %d paragraphs",
            len(asg.data_fields),
            len(asg.sections),
            len(asg.paragraphs),
        )
        return asg

    def _enrich_copybook_error(self, error: CobolParseError) -> CobolParseError:
        """Turn ProLeap's raw 'Could not find copy book X' into a clean message."""
        msg = str(error)
        if "Could not find copy book" not in msg:
            return error
        match = re.search(r"Could not find copy book (\S+)", msg)
        name = match.group(1) if match else "<unknown>"
        searched = [str(d) for d in self._copybook_dirs] or ["(none configured)"]
        return CobolParseError(
            f"Copybook {name!r} not found. Searched directories: {searched}"
        )
