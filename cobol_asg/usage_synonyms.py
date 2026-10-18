"""A USAGE as ProLeap's ASG names it, read as the one USAGE lowering knows it by."""

from __future__ import annotations

from types import MappingProxyType

_DISPLAY = "DISPLAY"

_CANONICAL = MappingProxyType(
    {
        "COMP_3": "COMP-3",
        "PACKED_DECIMAL": "COMP-3",
        "COMP": "COMP",
        "COMP_4": "COMP",
        "BINARY": "COMP",
        "COMP_1": "COMP-1",
        "COMP_2": "COMP-2",
        "COMP_5": "COMP-5",
        "DISPLAY_1": "DISPLAY-1",
        "INDEX": "INDEX",
        "NATIONAL": "NATIONAL",
        "POINTER": "POINTER",
        "COMP-3": "COMP-3",
        "COMP-1": "COMP-1",
        "COMP-2": "COMP-2",
        "COMP-5": "COMP-5",
        "DISPLAY-1": "DISPLAY-1",
    }
)


def canonical_usage(written: str) -> str:
    """COMP-4 and BINARY are COMP, PACKED-DECIMAL is COMP-3 (IBM Enterprise COBOL LR,
    USAGE clause); a USAGE lowering does not model is DISPLAY. Canonical names
    read as themselves, so an ASG revived from to_dict reads the same."""
    return _CANONICAL.get(written, _DISPLAY)
