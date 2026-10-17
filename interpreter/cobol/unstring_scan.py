"""UNSTRING's examination of the source (ANSI X3.23-1985 UNSTRING general rules).

Examination starts at the pointer. For each receiver in turn, the characters up
to the nearest delimiter occurrence go to it; where several delimiters match at
one position the first written wins, and an ALL delimiter takes the whole run
of its contiguous occurrences. Without delimiters each receiver takes as many
characters as its size. Examination stops when the source is exhausted or every
receiver has been acted on. The overflow condition arises when the pointer is
below 1 or past the source before examination, or when characters remain
unexamined after the last receiver.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial, reduce
from itertools import count

from interpreter.cobol.unstring_delimiter_text import UnstringDelimiterText
from interpreter.cobol.unstring_outcome import UnstringOutcome
from interpreter.cobol.unstring_piece import UnstringPiece

_NO_DELIMITER = UnstringDelimiterText(text="", all=False)

type _ScanState = tuple[int, tuple[UnstringPiece, ...]]


def _nearest(
    source: str, position: int, delimiters: Sequence[UnstringDelimiterText]
) -> tuple[int, UnstringDelimiterText]:
    return next(
        (
            (start, delimiter)
            for start in range(position, len(source))
            for delimiter in delimiters
            if delimiter.text and source.startswith(delimiter.text, start)
        ),
        (len(source), _NO_DELIMITER),
    )


def _run_end(source: str, start: int, delimiter: UnstringDelimiterText) -> int:
    width = len(delimiter.text)
    if not delimiter.all:
        return start + width
    repeats = next(
        n for n in count(1) if not source.startswith(delimiter.text, start + n * width)
    )
    return start + repeats * width


def _delimited_step(
    source: str, delimiters: Sequence[UnstringDelimiterText], position: int
) -> tuple[int, UnstringPiece]:
    start, delimiter = _nearest(source, position, delimiters)
    text = source[position:start]
    return (
        _run_end(source, start, delimiter),
        UnstringPiece(text=text, delimiter=delimiter.text, count=len(text)),
    )


def _sized_step(source: str, size: int, position: int) -> tuple[int, UnstringPiece]:
    text = source[position : position + size]
    return position + len(text), UnstringPiece(text=text, delimiter="", count=len(text))


def _step(
    source: str,
    delimiters: Sequence[UnstringDelimiterText],
    state: _ScanState,
    size: int,
) -> _ScanState:
    position, pieces = state
    if position >= len(source):
        return state
    end, piece = (
        _delimited_step(source, delimiters, position)
        if delimiters
        else _sized_step(source, size, position)
    )
    return end, (*pieces, piece)


def unstring(
    source: str,
    pointer: int,
    delimiters: Sequence[UnstringDelimiterText],
    sizes: Sequence[int],
) -> UnstringOutcome:
    if pointer < 1 or pointer > len(source):
        return UnstringOutcome(pieces=(), pointer=pointer, overflow=True)
    end, pieces = reduce(partial(_step, source, delimiters), sizes, (pointer - 1, ()))
    return UnstringOutcome(pieces=pieces, pointer=end + 1, overflow=end < len(source))
