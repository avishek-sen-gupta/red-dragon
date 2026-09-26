"""Deliberate command-line output.

Ruff's T201 bans bare `print` because it "is not configurable by clients, unlike
logging statements". Logging is the wrong substitute for a CLI's *product*,
though: `interpreter.py --mermaid` is piped into a .mmd file and `--ir-only`
into a diff, and a logger would send both to stderr, level-filter them and
prefix each line with a timestamp. Ruff's own fix is worse still — it deletes
the print, and with it the `dump_ir(...)` call that was its argument.

So program output goes through here: one place that decides the stream, and one
that a test can redirect without capturing global stdout. Diagnostics still
belong in `logging` — `emit_err` is for a CLI reporting its own failure to a
user, not for tracing.

Ruff exempts `print(..., file=<some stream>)` already -- writing to a stream the
caller supplied is not console output -- so there is no wrapper for that case.

This module imports nothing from the rest of the interpreter, so any package or
script may depend on it.
"""

from __future__ import annotations

import sys
from typing import TextIO


def _write(stream: TextIO, parts: tuple[object, ...], sep: str, end: str) -> None:
    stream.write(sep.join(str(part) for part in parts) + end)


def emit(*parts: object, sep: str = " ", end: str = "\n") -> None:
    """Write program output to stdout. The CLI equivalent of `print`."""
    _write(sys.stdout, parts, sep, end)


def emit_err(*parts: object, sep: str = " ", end: str = "\n") -> None:
    """Write a user-facing diagnostic to stderr."""
    _write(sys.stderr, parts, sep, end)
