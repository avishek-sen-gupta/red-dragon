"""Where an INSPECT scan has got to, and what it has matched so far."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InspectScanState:
    """The next unexamined position, the matches made, and per phrase the
    position a LEADING match must be at and whether a FIRST has matched."""

    cursor: int
    matches: tuple[tuple[int, int], ...]
    leading_next: tuple[int, ...]
    first_done: tuple[bool, ...]

    def matched(self, phrase: int, position: int, length: int) -> InspectScanState:
        return InspectScanState(
            cursor=position + length,
            matches=(*self.matches, (phrase, position)),
            leading_next=tuple(
                position + length if index == phrase else expected
                for index, expected in enumerate(self.leading_next)
            ),
            first_done=tuple(
                done or index == phrase for index, done in enumerate(self.first_done)
            ),
        )
