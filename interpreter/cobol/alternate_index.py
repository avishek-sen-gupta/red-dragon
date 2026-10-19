"""One alternate record key's index over an indexed file: each record's value of that key,
the order the value was stored in, and the record's prime key, kept sorted by value and
then by order."""

from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from interpreter.cobol.alternate_key import AlternateKey

type IndexEntry = tuple[bytes, int, bytes]


def _value(entry: IndexEntry) -> bytes:
    return entry[0]


def _leading(length: int) -> Callable[[IndexEntry], bytes]:
    return lambda entry: entry[0][:length]


def after(entry: IndexEntry) -> IndexEntry:
    return entry[0], entry[1] + 1, b""


@dataclass(frozen=True)
class AlternateIndex:
    key: AlternateKey
    entries: tuple[IndexEntry, ...] = ()

    def value_of(self, record: bytes) -> bytes:
        return self.key.key.of(record)

    def stored(self, record: bytes, order: int, prime: bytes) -> AlternateIndex:
        entry = (self.value_of(record), order, prime)
        slot = bisect.bisect_left(self.entries, entry)
        return AlternateIndex(
            self.key, (*self.entries[:slot], entry, *self.entries[slot:])
        )

    def without(self, prime: bytes) -> AlternateIndex:
        return AlternateIndex(self.key, tuple(e for e in self.entries if e[2] != prime))

    def holds(self, value: bytes) -> bool:
        slot = bisect.bisect_left(self.entries, value, key=_value)
        return slot < len(self.entries) and self.entries[slot][0] == value

    def refuses(self, value: bytes) -> bool:
        return self.key.unique and self.holds(value)

    def repeats(self, value: bytes) -> bool:
        return not self.key.unique and self.holds(value)

    def next_from(self, place: IndexEntry) -> int:
        return bisect.bisect_left(self.entries, place)

    def follows(self, slot: int) -> bool:
        nxt = slot + 1
        return nxt < len(self.entries) and self.entries[nxt][0] == self.entries[slot][0]

    def first_leading(self, value: bytes, past: bool) -> int:
        leading = _leading(len(value))
        if past:
            return bisect.bisect_right(self.entries, value, key=leading)
        return bisect.bisect_left(self.entries, value, key=leading)


def indexes_of(
    keys: Sequence[AlternateKey], records: Sequence[tuple[bytes, bytes]]
) -> tuple[AlternateIndex, ...]:
    return tuple(
        AlternateIndex(
            key,
            tuple(
                sorted(
                    (key.key.of(record), order, prime)
                    for order, (record, prime) in enumerate(records)
                )
            ),
        )
        for key in keys
    )
