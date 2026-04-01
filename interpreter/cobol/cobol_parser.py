# pyright: standard
"""COBOL parser — subprocess bridge to ProLeap.

The ProLeap bridge is a separate Java repo that parses COBOL source
using ANTLR4 and emits JSON ASG to stdout. This module wraps the
subprocess call and deserializes the JSON into CobolASG.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.subprocess_runner import SubprocessRunner

logger = logging.getLogger(__name__)


class CobolParser(ABC):
    """Abstract COBOL parser interface."""

    @abstractmethod
    def parse(self, source: bytes) -> CobolASG:
        """Parse COBOL source bytes into an ASG."""
        ...


class ProLeapCobolParser(CobolParser):
    """COBOL parser that delegates to the ProLeap bridge via subprocess."""

    def __init__(self, runner: SubprocessRunner, bridge_jar: str):
        self._runner = runner
        self._bridge_jar = bridge_jar

    def parse(self, source: bytes) -> CobolASG:
        logger.info("Parsing COBOL source (%d bytes) via ProLeap bridge", len(source))
        json_str = self._runner.run(
            ["java", "-jar", self._bridge_jar],
            source.decode("utf-8"),
        )
        data = json.loads(json_str)
        asg = CobolASG.from_dict(data)
        logger.info(
            "Parsed ASG: %d data fields, %d sections, %d paragraphs",
            len(asg.data_fields),
            len(asg.sections),
            len(asg.paragraphs),
        )
        return asg
