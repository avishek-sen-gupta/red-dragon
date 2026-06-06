"""CICS shared runtime types — CicsContext, DispatchResult, DispatchKind."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass
class CicsContext:
    """Runtime state passed into each CICS program execution."""

    transid: str
    commarea: bytes
    eibaid: str  # 1-char attention identifier (e.g. "\x7d" = DFHENTER)


class DispatchKind(Enum):
    RETURN = "return"
    RETURN_TRANSID = "return_transid"
    XCTL = "xctl"
    ABEND = "abend"


@dataclass
class DispatchResult:
    """Result returned by run_cics() to the dispatcher loop."""

    kind: DispatchKind
    transid: str | None = None  # RETURN_TRANSID
    commarea: bytes | None = None  # RETURN_TRANSID, XCTL
    program: str | None = None  # XCTL
    abcode: str | None = None  # ABEND
