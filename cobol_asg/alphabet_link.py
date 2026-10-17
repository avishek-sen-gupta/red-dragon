"""How an ALPHABET literal joins the literal written before it."""

from enum import StrEnum


class AlphabetLink(StrEnum):
    """NONE starts a new position, THRU ends a range, ALSO shares a position."""

    NONE = "NONE"
    THRU = "THRU"
    ALSO = "ALSO"
