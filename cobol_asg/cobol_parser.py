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
from collections.abc import Callable, Sequence
from pathlib import Path

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.compilation_unit import CobolCompilationUnit
from cobol_asg.copybook_library import CopybookLibrary
from cobol_asg.copybook_search import NO_COPYBOOK_SEARCH, CopybookSearch
from cobol_asg.lp32 import LP32_MODE
from cobol_asg.source_text import decode_source
from cobol_asg.subprocess_runner import (
    CobolParseError,
    RealSubprocessRunner,
    SubprocessRunner,
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
    ) -> CobolCompilationUnit:
        """Parse COBOL source bytes into the compilation unit of its programs.

        *preprocessor* is called on each program's raw bridge JSON dict, in
        pre-order, before :func:`CobolASG.from_dict` runs — used by the CICS
        strategy to resolve CICS-specific expression nodes into generic ones.
        """
        ...


class ProLeapCobolParser(CobolParser):
    """COBOL parser that delegates to the ProLeap bridge via subprocess."""

    def __init__(
        self,
        runner: SubprocessRunner,
        bridge_jar: str,
        copybooks: CopybookSearch = NO_COPYBOOK_SEARCH,
        addressing_mode: AddressingMode = LP32_MODE,
    ):
        self._runner = runner
        self._bridge_jar = bridge_jar
        self._copybooks = copybooks
        self._addressing_mode = addressing_mode

    def with_addressing_mode(self, mode: AddressingMode) -> ProLeapCobolParser:
        """The same parser, laying out USAGE POINTER items for ``mode``."""
        return ProLeapCobolParser(
            self._runner,
            self._bridge_jar,
            self._copybooks,
            mode,
        )

    def _build_command(self) -> list[str]:
        dirs = [arg for d in self._copybooks.dirs for arg in ("-copybook-dir", str(d))]
        exts = [arg for e in self._copybooks.exts for arg in ("-copybook-ext", e)]
        libraries = [
            arg
            for library in self._copybooks.libraries
            for arg in ("-copybook-library", library.name, str(library.directory))
        ]
        return ["java", "-jar", self._bridge_jar, *dirs, *exts, *libraries]

    def parse(
        self,
        source: bytes,
        preprocessor: Callable[[dict], dict] = _IDENTITY,
    ) -> CobolCompilationUnit:
        logger.debug("Parsing COBOL source (%d bytes) via ProLeap bridge", len(source))
        command = self._build_command()
        try:
            json_str = self._runner.run(command, decode_source(source))
        except CobolParseError as e:
            raise self._enrich_copybook_error(e) from e
        unit = CobolCompilationUnit.from_dict(
            json.loads(json_str), self._addressing_mode, preprocessor
        )
        logger.debug("Parsed compilation unit: %d programs", len(unit.programs))
        return unit

    def expand(self, source: bytes) -> str:
        """The preprocessed source: copybooks inlined, continuations folded.

        The text the ANTLR lexer is handed, and nothing past it -- the bridge
        stops before the COBOL grammar runs, so this answers "what did the
        compiler actually see" for a member whose parse fails.
        """
        command = [*self._build_command(), "-expand-only"]
        try:
            return self._runner.run(command, decode_source(source))
        except CobolParseError as e:
            raise self._enrich_copybook_error(e) from e

    def parse_to_file(self, source: bytes, out_path: Path) -> Path:
        """Run the bridge and write raw JSON to out_path. Returns out_path.

        The JSON string is freed immediately after writing — never returned —
        so callers cannot accumulate it when running in parallel.
        """
        command = self._build_command()
        try:
            json_str = self._runner.run(command, decode_source(source))
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
        searched = [str(d) for d in self._copybooks.dirs] or ["(none configured)"]
        return CobolParseError(
            f"Copybook not found (searched directories: {searched}). "
            f"Underlying parser error: {msg}"
        )


def make_cobol_parser(
    copybook_dirs: Sequence[Path] = (),
    copybook_exts: Sequence[str] = (),
    copybook_libraries: Sequence[CopybookLibrary] = (),
) -> ProLeapCobolParser:
    """Construct a ProLeapCobolParser from PROLEAP_BRIDGE_JAR env var.

    Falls back to the canonical build output path when the env var is unset.
    """
    bridge_jar = os.environ.get(
        "PROLEAP_BRIDGE_JAR",
        "proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar",
    )
    return ProLeapCobolParser(
        RealSubprocessRunner(),
        bridge_jar,
        CopybookSearch(
            tuple(copybook_dirs), tuple(copybook_exts), tuple(copybook_libraries)
        ),
    )
