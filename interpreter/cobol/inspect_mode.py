"""How an INSPECT phrase matches: ALL, LEADING, FIRST or CHARACTERS."""

from enum import Enum


class InspectMode(Enum):
    """The phrase keyword of an INSPECT TALLYING or REPLACING phrase."""

    ALL = "ALL"
    LEADING = "LEADING"
    FIRST = "FIRST"
    CHARACTERS = "CHARACTERS"
