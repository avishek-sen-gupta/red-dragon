"""An EXEC85 *OPT selection: the optional-code variant a CCVS program is run with."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OptionSelection:
    """The selected variant's letter, and the sequence numbers of its cards."""

    letter: str
    cards: frozenset[str]
