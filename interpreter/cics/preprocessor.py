"""CICS text pre-pass — runs before ProLeap parses COBOL source."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Canonical CICS DFHRESP / EIBRESP code set. The contiguous 0-44 block is the
# standard IBM-documented EIBRESP value set; every code is unique so that two
# distinct conditions can never compare-equal after substitution. Higher codes
# below are additional names the translator output references.
_DFHRESP_TABLE: dict[str, int] = {
    # --- Standard contiguous EIBRESP set (0-44) ---
    "NORMAL": 0,
    "ERROR": 1,
    "RDATT": 2,
    "WRBRK": 3,
    "EOF": 4,
    "EODS": 5,
    "EOC": 6,
    "INBFMH": 7,
    "ENDINPT": 8,
    "NONVAL": 9,
    "NOSTART": 10,
    "TERMIDERR": 11,
    "FILENOTFOUND": 12,
    "NOTFND": 13,
    "DUPREC": 14,
    "DUPKEY": 15,
    "INVREQ": 16,
    "IOERR": 17,
    "NOSPACE": 18,
    "NOTOPEN": 19,
    "ENDFILE": 20,
    "ILLOGIC": 21,
    "LENGERR": 22,
    "QZERO": 23,
    "SIGNAL": 24,
    "QBUSY": 25,
    "ITEMERR": 26,
    "PGMIDERR": 27,
    "TRANSIDERR": 28,
    "ENDDATA": 29,
    "INVTSREQ": 30,
    "EXPIRED": 31,
    "RETPAGE": 32,
    "RTEFAIL": 33,
    "RTESOME": 34,
    "TSIOERR": 35,
    "MAPFAIL": 36,
    "INVERRTERM": 37,
    "INVMPSZ": 38,
    "IGREQID": 39,
    "OVERFLOW": 40,
    "INVLDC": 41,
    "NOSTG": 42,
    "JIDERR": 43,
    "QIDERR": 44,
    # --- Additional names referenced by translator output (higher codes) ---
    "SYSIDERR": 53,
    "ISCINVREQ": 54,
    "SYSBUSY": 79,
    "TERMERR": 81,
    "SESSIONERR": 82,
    "DISABLED": 84,
    # --- De-collided non-standard names (kept for compatibility, unused) ---
    "LENOVF": 522,  # was 27, which collides with PGMIDERR
    "UNEXPIN": 523,  # non-standard; canonical 35 collides with TSIOERR, kept distinct
}

# Sentinel for unknown/typo'd conditions. Chosen so it can never equal a real
# EIBRESP value a program checks — substituting 0 (=NORMAL) would let a bogus
# condition silently masquerade as the normal path.
_DFHRESP_UNKNOWN = 9999

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
            logger.warning(
                "Unknown DFHRESP condition %r — substituting sentinel %d "
                "(will never match a real response)",
                name,
                _DFHRESP_UNKNOWN,
            )
            return str(_DFHRESP_UNKNOWN)
        return str(_DFHRESP_TABLE[name])

    return _DFHRESP_RE.sub(_replace, source)


def apply_cics_prepass(source: str) -> str:
    """Apply all CICS pre-pass transformations to COBOL source."""
    source = inject_dfheiblk(source)
    source = substitute_dfhresp(source)
    return source
