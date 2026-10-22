# pyright: standard
"""An immutable cons-list: extending it is O(1) and shares the chain it extends."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import accumulate, chain

from interpreter.hlasm.empty_chain import EmptyChain


@dataclass(frozen=True)
class ChainLink[T]:
    """One item on top of the chain before it."""

    previous: Chain[T]
    item: T
    length: int

    def items(self) -> tuple[T, ...]:
        return (self.item,)


type Chain[T] = ChainLink[T] | EmptyChain[T]


def extended[T](before: Chain[T], item: T) -> ChainLink[T]:
    return ChainLink(before, item, before.length + 1)


def _back[T](link: Chain[T], _: int) -> Chain[T]:
    return link.previous


def flattened[T](last: Chain[T]) -> tuple[T, ...]:
    links = accumulate(range(last.length - 1), _back, initial=last)
    return tuple(chain.from_iterable(link.items() for link in reversed(list(links))))
