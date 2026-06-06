"""CICS text pre-pass — runs before ProLeap parses COBOL source."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_DFHRESP_TABLE: dict[str, int] = {
    "NORMAL": 0,
    "NOTFND": 13,
    "ENDFILE": 20,
    "DUPREC": 14,
    "DISABLED": 84,
    "ILLOGIC": 21,
    "IOERR": 17,
    "LENOVF": 522,  # was 27, which collides with PGMIDERR
    "LENGERR": 22,
    "NOSPACE": 18,
    "NOTOPEN": 19,
    "PGMIDERR": 27,
    "QIDERR": 44,
    "TRANSIDERR": 28,
    "INVREQ": 16,
    "MAPFAIL": 36,
    "UNEXPIN": 35,
    "TERMERR": 81,
    "SESSIONERR": 82,
    "SYSBUSY": 79,
    "SYSIDERR": 53,
    "ISCINVREQ": 54,
}

_WS_SECTION_RE = re.compile(r"^(\s*)WORKING-STORAGE\s+SECTION\s*\.", re.IGNORECASE)
_DFHRESP_RE = re.compile(r"DFHRESP\((\w+)\)", re.IGNORECASE)

# 7 spaces = Area A (column 8); valid for COPY, matches IBM CICS translator output
_DFHEIBLK_COPY = "       COPY DFHEIBLK."


def inject_dfheiblk(source: str) -> str:
    """Insert COPY DFHEIBLK. on the line immediately after WORKING-STORAGE SECTION."""
    lines = source.splitlines(keepends=True)
    result: list[str] = []
    injected = False
    for line in lines:
        result.append(line)
        if not injected and _WS_SECTION_RE.match(line):
            ending = "\r\n" if line.endswith("\r\n") else "\n"
            result.append(_DFHEIBLK_COPY + ending)
            injected = True
    return "".join(result)


def substitute_dfhresp(source: str) -> str:
    """Replace DFHRESP(name) with its numeric response code."""

    def _replace(m: re.Match) -> str:
        name = m.group(1).upper()
        if name not in _DFHRESP_TABLE:
            logger.warning("Unknown DFHRESP condition %r — substituting 0", name)
        return str(_DFHRESP_TABLE.get(name, 0))

    return _DFHRESP_RE.sub(_replace, source)


def apply_cics_prepass(source: str) -> str:
    """Apply all CICS pre-pass transformations to COBOL source."""
    source = inject_dfheiblk(source)
    source = substitute_dfhresp(source)
    return source
