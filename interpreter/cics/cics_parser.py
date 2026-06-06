"""Parse EXEC CICS text into (verb, options) for ExecCicsStatement."""

from __future__ import annotations

import re

# Compound verbs detected by first word + second word prefix
_COMPOUND_FIRST = {"SEND", "RECEIVE", "HANDLE"}
_COMPOUND_SECOND: dict[str, set[str]] = {
    "SEND": {"MAP", "TEXT"},
    "RECEIVE": {"MAP"},
    "HANDLE": {"ABEND", "CONDITION", "AID"},
}

_EXEC_CICS_PREFIX = re.compile(r"^\s*EXEC\s+CICS\s+", re.IGNORECASE)
_END_EXEC_SUFFIX = re.compile(r"\s*END-EXEC\s*$", re.IGNORECASE)
_OPTION_RE = re.compile(r"([A-Z][A-Z0-9-]*)(?:\(([^)]*)\))?", re.IGNORECASE)


def parse_exec_cics_text(text: str) -> tuple[str, dict[str, str | None]]:
    """Parse 'EXEC CICS VERB OPT1(val) FLAG END-EXEC' → (verb, {OPT1: val, FLAG: None})."""
    body = _EXEC_CICS_PREFIX.sub("", text.strip())
    body = _END_EXEC_SUFFIX.sub("", body).strip()

    if not body:
        return "", {}

    words = body.split()
    first = words[0].upper()

    if first in _COMPOUND_FIRST and len(words) >= 2:
        second_prefix = words[1].split("(")[0].upper()
        if second_prefix in _COMPOUND_SECOND.get(first, set()):
            verb = f"{first} {second_prefix}"
            options_body = body[len(words[0]) :].strip()
            return verb, _parse_options(options_body)

    options_body = body[len(words[0]) :].strip()
    return first, _parse_options(options_body)


def _parse_options(text: str) -> dict[str, str | None]:
    options: dict[str, str | None] = {}
    for m in _OPTION_RE.finditer(text):
        key = m.group(1).upper()
        val = m.group(2)
        if val is not None:
            val = val.strip().strip("'\"")
        options[key] = val
    return options
