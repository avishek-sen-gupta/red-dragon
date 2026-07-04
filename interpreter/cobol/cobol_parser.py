# pyright: standard
"""COBOL parser — subprocess bridge to ProLeap.

The ProLeap bridge is a separate Java repo that parses COBOL source
using ANTLR4 and emits JSON ASG to stdout. This module wraps the
subprocess call and deserializes the JSON into CobolASG.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.subprocess_runner import (
    SubprocessRunner,
    CobolParseError,
    RealSubprocessRunner,
)

logger = logging.getLogger(__name__)

_IDENTITY: Callable[[dict], dict] = lambda d: d  # noqa: E731


class CobolParser(ABC):
    """Abstract COBOL parser interface."""

    @abstractmethod
    def parse(
        self,
        source: bytes,
        preprocessor: Callable[[dict], dict] = _IDENTITY,
    ) -> CobolASG:
        """Parse COBOL source bytes into an ASG.

        *preprocessor* is called on the raw bridge JSON dict before
        :func:`CobolASG.from_dict` runs — used by the CICS strategy to
        resolve CICS-specific expression nodes into generic ones.
        """
        ...


class ProLeapCobolParser(CobolParser):
    """COBOL parser that delegates to the ProLeap bridge via subprocess."""

    def __init__(
        self,
        runner: SubprocessRunner,
        bridge_jar: str,
        copybook_dirs: list[Path] = [],
    ):
        self._runner = runner
        self._bridge_jar = bridge_jar
        self._copybook_dirs: list[Path] = list(copybook_dirs or [])

    def _build_command(self) -> list[str]:
        command = ["java", "-jar", self._bridge_jar]
        for d in self._copybook_dirs:
            command += ["-copybook-dir", str(d)]
        return command

    def parse(
        self,
        source: bytes,
        preprocessor: Callable[[dict], dict] = _IDENTITY,
    ) -> CobolASG:
        logger.debug("Parsing COBOL source (%d bytes) via ProLeap bridge", len(source))
        command = self._build_command()
        try:
            json_str = self._runner.run(command, source.decode("utf-8"))
        except CobolParseError as e:
            raise self._enrich_copybook_error(e) from e
        data: dict = json.loads(json_str)
        data = preprocessor(data)
        asg = CobolASG.from_dict(data)
        logger.debug(
            "Parsed ASG: %d data fields, %d sections, %d paragraphs",
            len(asg.data_fields),
            len(asg.sections),
            len(asg.paragraphs),
        )
        return asg

    def parse_to_file(self, source: bytes, out_path: Path) -> Path:
        """Run the bridge and write raw JSON to out_path. Returns out_path.

        The JSON string is freed immediately after writing — never returned —
        so callers cannot accumulate it when running in parallel.
        """
        command = self._build_command()
        try:
            json_str = self._runner.run(command, source.decode("utf-8"))
        except CobolParseError as e:
            raise self._enrich_copybook_error(e) from e
        out_path.write_text(json_str, encoding="utf-8")
        return out_path

    def _enrich_copybook_error(self, error: CobolParseError) -> CobolParseError:
        """Add the searched copybook directories to a 'copy book not found' error.

        The underlying ProLeap message (which names the missing copybook) is
        surfaced verbatim rather than regex-scraped for the name — we don't parse
        a message we don't own. The original error is chained as ``__cause__`` by
        the caller's ``raise ... from`` (red-dragon-vgm5).
        """
        msg = str(error)
        if "Could not find copy book" not in msg:
            return error
        searched = [str(d) for d in self._copybook_dirs] or ["(none configured)"]
        return CobolParseError(
            f"Copybook not found (searched directories: {searched}). "
            f"Underlying parser error: {msg}"
        )


def make_cobol_parser(
    copybook_dirs: list[Path] = [],
) -> ProLeapCobolParser:
    """Construct a ProLeapCobolParser from PROLEAP_BRIDGE_JAR env var.

    Falls back to the canonical build output path when the env var is unset.
    """
    bridge_jar = os.environ.get(
        "PROLEAP_BRIDGE_JAR",
        "proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar",
    )
    return ProLeapCobolParser(
        RealSubprocessRunner(), bridge_jar, copybook_dirs=copybook_dirs
    )
