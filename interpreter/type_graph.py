"""TypeGraph — DAG of types with subtype queries and least-upper-bound."""

from __future__ import annotations

import logging
from collections import deque
from functools import reduce

from interpreter.type_node import TypeNode
from interpreter.constants import TypeName

logger = logging.getLogger(__name__)


DEFAULT_TYPE_NODES: tuple[TypeNode, ...] = (
    TypeNode(name=TypeName.ANY, parents=()),
    TypeNode(name=TypeName.NUMBER, parents=(TypeName.ANY,)),
    TypeNode(name=TypeName.STRING, parents=(TypeName.ANY,)),
    TypeNode(name=TypeName.BOOL, parents=(TypeName.ANY,)),
    TypeNode(name=TypeName.OBJECT, parents=(TypeName.ANY,)),
    TypeNode(name=TypeName.ARRAY, parents=(TypeName.ANY,)),
    TypeNode(name=TypeName.INT, parents=(TypeName.NUMBER,)),
    TypeNode(name=TypeName.FLOAT, parents=(TypeName.NUMBER,)),
)


class TypeGraph:
    """Immutable DAG of types supporting subtype checks and LUB queries.

    Constructed from a tuple of TypeNode values. Use extend() to produce
    a new graph with additional nodes without mutating the original.
    """

    def __init__(self, nodes: tuple[TypeNode, ...]) -> None:
        self._nodes: dict[str, TypeNode] = {node.name: node for node in nodes}

    def contains(self, type_name: str) -> bool:
        return type_name in self._nodes

    def is_subtype(self, child: str, parent: str) -> bool:
        """Return True if child is a subtype of parent (transitive, reflexive)."""
        if child == parent:
            return True
        if child not in self._nodes:
            return False
        if parent not in self._nodes:
            return False
        visited: set[str] = set()
        queue: deque[str] = deque([child])
        while queue:
            current = queue.popleft()
            if current == parent:
                return True
            if current in visited:
                continue
            visited.add(current)
            node = self._nodes.get(current)
            if node:
                queue.extend(node.parents)
        return False

    def _ancestors(self, type_name: str) -> list[str]:
        """Return all ancestors of type_name in BFS order, including itself."""
        result: list[str] = []
        visited: set[str] = set()
        queue: deque[str] = deque([type_name])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            result.append(current)
            node = self._nodes.get(current)
            if node:
                queue.extend(node.parents)
        return result

    def common_supertype(self, type_a: str, type_b: str) -> str:
        """Return the least upper bound (closest common ancestor) of two types.

        Returns TypeName.ANY for unknown types.
        """
        if type_a == type_b:
            return type_a
        if type_a not in self._nodes or type_b not in self._nodes:
            return TypeName.ANY
        ancestors_a = self._ancestors(type_a)
        ancestors_b_set = set(self._ancestors(type_b))
        common = [a for a in ancestors_a if a in ancestors_b_set]
        return common[0] if common else TypeName.ANY

    def extend(self, additional: tuple[TypeNode, ...]) -> "TypeGraph":
        """Return a new TypeGraph with the additional nodes merged in."""
        merged = self._nodes.copy()
        for node in additional:
            merged[node.name] = node
        return TypeGraph(tuple(merged.values()))
