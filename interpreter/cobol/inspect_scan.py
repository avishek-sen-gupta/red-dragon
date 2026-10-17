"""The INSPECT statement's scan (ANSI X3.23-1985 INSPECT general rules).

The inspected item is examined left to right once. At each position the
phrases are tried in the order written; the first that matches there, inside
its own BEFORE / AFTER region, is applied and the scan resumes after the
matched characters. When none matches the scan moves one position right.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import reduce

from interpreter.cobol.inspect_mode import InspectMode
from interpreter.cobol.inspect_phrase import InspectPhrase
from interpreter.cobol.inspect_scan_state import InspectScanState


def _matches_at(
    source: str,
    phrase: InspectPhrase,
    region: tuple[int, int],
    position: int,
    expected: tuple[int, bool],
) -> bool:
    start, end = region
    length = phrase.length()
    leading_at, first_done = expected
    return (
        length > 0
        and start <= position
        and position + length <= end
        and (
            phrase.mode == InspectMode.CHARACTERS
            or source[position : position + length] == phrase.pattern
        )
        and (phrase.mode != InspectMode.LEADING or position == leading_at)
        and not (phrase.mode == InspectMode.FIRST and first_done)
    )


def _scan(source: str, phrases: Sequence[InspectPhrase]) -> tuple[tuple[int, int], ...]:
    regions = tuple(phrase.region(source) for phrase in phrases)

    def step(state: InspectScanState, position: int) -> InspectScanState:
        if position < state.cursor:
            return state
        hit = next(
            (
                index
                for index, phrase in enumerate(phrases)
                if _matches_at(
                    source,
                    phrase,
                    regions[index],
                    position,
                    (state.leading_next[index], state.first_done[index]),
                )
            ),
            -1,
        )
        if hit < 0:
            return state
        return state.matched(hit, position, phrases[hit].length())

    initial = InspectScanState(
        cursor=0,
        matches=(),
        leading_next=tuple(start for start, _ in regions),
        first_done=tuple(False for _ in phrases),
    )
    return reduce(step, range(len(source)), initial).matches


def inspect_tally(
    source: str, phrases: Sequence[InspectPhrase], counters: int
) -> tuple[int, ...]:
    """How many matches each TALLYING identifier gains."""
    owners = [phrases[phrase].counter for phrase, _ in _scan(source, phrases)]
    return tuple(owners.count(counter) for counter in range(counters))


def inspect_replace(source: str, phrases: Sequence[InspectPhrase]) -> str:
    """``source`` with every matched run replaced by its phrase's BY value."""
    return reduce(
        lambda text, match: _splice(text, match, phrases[match[0]]),
        _scan(source, phrases),
        source,
    )


def _splice(text: str, match: tuple[int, int], phrase: InspectPhrase) -> str:
    _, position = match
    return (
        text[:position]
        + phrase.fitted_replacement()
        + text[position + phrase.length() :]
    )


def inspect_convert(
    source: str, from_chars: str, to_chars: str, after: str, before: str
) -> str:
    """CONVERTING: each character of ``from_chars`` inside the region becomes
    the ``to_chars`` character at the position of its first occurrence."""
    start, end = InspectPhrase(
        InspectMode.CHARACTERS, after=after, before=before
    ).region(source)
    table = {
        char: to_chars[from_chars.index(char)]
        for char in from_chars
        if from_chars.index(char) < len(to_chars)
    }
    return (
        source[:start]
        + "".join(table.get(char, char) for char in source[start:end])
        + source[end:]
    )
