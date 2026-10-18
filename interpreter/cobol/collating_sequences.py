"""Builds a program's collating sequence from the ALPHABET clause it names."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import reduce

from cobol_asg.alphabet import Alphabet
from cobol_asg.alphabet_item import AlphabetItem
from cobol_asg.alphabet_kind import AlphabetKind
from cobol_asg.alphabet_link import AlphabetLink
from cobol_asg.alphabet_literal_kind import AlphabetLiteralKind
from interpreter.cobol.collating_sequence import CollatingSequence
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.figurative_constants import COBOL_FIGURATIVE_CONSTANTS

Positions = tuple[tuple[int, ...], ...]

_NATIVE_BYTES = range(256)


def _native_byte(character: str) -> int:
    return EbcdicTable.ASCII_TO_EBCDIC[ord(character)]


def literal_native_bytes(item: AlphabetItem) -> tuple[int, ...]:
    """The native bytes a literal names: a numeric literal is an ordinal position."""
    if item.kind == AlphabetLiteralKind.NUMERIC:
        return (int(item.value) - 1,)
    if item.kind == AlphabetLiteralKind.FIGURATIVE:
        return (_native_byte(COBOL_FIGURATIVE_CONSTANTS[item.value]),)
    return tuple(_native_byte(c) for c in item.value)


def _new_positions(positions: Positions, item: AlphabetItem) -> Positions:
    return (*positions, *((b,) for b in literal_native_bytes(item)))


def _through(positions: Positions, item: AlphabetItem) -> Positions:
    start, end = positions[-1][-1], literal_native_bytes(item)[0]
    step = 1 if end >= start else -1
    return (*positions, *((b,) for b in range(start + step, end + step, step)))


def _also(positions: Positions, item: AlphabetItem) -> Positions:
    return (*positions[:-1], (*positions[-1], *literal_native_bytes(item)))


_LINKS: Mapping[AlphabetLink, Callable[[Positions, AlphabetItem], Positions]] = {
    AlphabetLink.NONE: _new_positions,
    AlphabetLink.THRU: _through,
    AlphabetLink.ALSO: _also,
}


def _sequence(positions: Positions) -> CollatingSequence:
    position_of = {b: n for n, bytes_ in enumerate(positions) for b in bytes_}
    return CollatingSequence(
        weights=tuple(position_of[b] for b in _NATIVE_BYTES),
        first_bytes=tuple(bytes_[0] for bytes_ in positions),
        low_value=positions[0][0],
        high_value=positions[-1][-1],
    )


def _literal_phrase(items: Sequence[AlphabetItem]) -> CollatingSequence:
    specified: Positions = reduce(
        lambda positions, item: _LINKS[item.link](positions, item), items, ()
    )
    named = {b for bytes_ in specified for b in bytes_}
    return _sequence((*specified, *((b,) for b in _NATIVE_BYTES if b not in named)))


def _ascii() -> CollatingSequence:
    return _sequence(
        tuple((EbcdicTable.ASCII_TO_EBCDIC[code],) for code in _NATIVE_BYTES)
    )


NATIVE_SEQUENCE = _sequence(tuple((b,) for b in _NATIVE_BYTES))

_ASCII_KINDS = frozenset(
    {AlphabetKind.ASCII, AlphabetKind.STANDARD_1, AlphabetKind.STANDARD_2}
)


def collating_sequence_of(alphabet: Alphabet) -> CollatingSequence:
    """ANSI X3.23-1985 VI-4.5.4: literals in ascending order, ALSO sharing a
    position, THRU a native range; unnamed characters follow in native order."""
    if alphabet.kind == AlphabetKind.LITERALS:
        return _literal_phrase(alphabet.items)
    if alphabet.kind in _ASCII_KINDS:
        return _ascii()
    return NATIVE_SEQUENCE
