"""TypeNode — a node in the type hierarchy DAG."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TypeNode:
    """A single type in the type hierarchy.

    Each node names its parent types, forming a DAG that TypeGraph
    traverses for subtype checks and least-upper-bound queries.

    ``kind`` distinguishes classes from interfaces/traits:
    - ``"class"`` (default): concrete type
    - ``"interface"``: abstract interface/trait type
    """

    name: str
    parents: tuple[str, ...] = ()
    kind: str = "class"
