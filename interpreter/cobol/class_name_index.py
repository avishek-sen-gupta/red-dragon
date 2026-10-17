"""ClassNameIndex — the character set each SPECIAL-NAMES class-name names."""

from __future__ import annotations

from collections.abc import Sequence
from functools import reduce

from cobol_asg.alphabet_item import AlphabetItem
from cobol_asg.alphabet_link import AlphabetLink
from cobol_asg.class_definition import ClassDefinition
from interpreter.cobol.collating_sequences import literal_native_bytes
from interpreter.cobol.ebcdic_table import EbcdicTable

_ClassBytes = tuple[frozenset[int], int]


def _with_item(found: _ClassBytes, item: AlphabetItem) -> _ClassBytes:
    named, last = found
    item_bytes = literal_native_bytes(item)
    if item.link == AlphabetLink.THRU:
        low, high = sorted((last, item_bytes[0]))
        return named | frozenset(range(low, high + 1)), item_bytes[-1]
    return named | frozenset(item_bytes), item_bytes[-1]


def _characters(definition: ClassDefinition) -> str:
    named, _ = reduce(_with_item, definition.items, (frozenset[int](), 0))
    return "".join(chr(EbcdicTable.EBCDIC_TO_ASCII[b]) for b in sorted(named))


class ClassNameIndex:
    """Each class-name's characters, in native order: the literals' characters,
    and for THRU every native character between the two, written in either
    order."""

    def __init__(self, classes: Sequence[ClassDefinition]) -> None:
        self._characters = {c.name.upper(): _characters(c) for c in classes}

    def has_class(self, name: str) -> bool:
        return name.upper() in self._characters

    def characters(self, name: str) -> str:
        return self._characters[name.upper()]
