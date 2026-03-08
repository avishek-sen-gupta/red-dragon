"""TypeGraph — DAG of types with subtype queries and least-upper-bound."""

from __future__ import annotations

import logging
from collections import deque
from functools import reduce

from interpreter.type_node import TypeNode
from interpreter.constants import TypeName
from interpreter.type_expr import (
    TypeExpr,
    ScalarType,
    ParameterizedType,
    UnionType,
    scalar,
    union_of,
)

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
    TypeNode(name=TypeName.POINTER, parents=(TypeName.ANY,)),
    TypeNode(name=TypeName.MAP, parents=(TypeName.ANY,)),
    TypeNode(name=TypeName.REGION, parents=(TypeName.ANY,)),
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

    # -------------------------------------------------------------------
    # TypeExpr-aware methods (parameterized type support)
    # -------------------------------------------------------------------

    def is_subtype_expr(self, child: TypeExpr, parent: TypeExpr) -> bool:
        """Check subtype relationship between two TypeExpr values.

        Rules (covariant):
        - UnionType child: all members must be subtypes of parent.
        - UnionType parent: child must be a subtype of at least one member.
        - ScalarType vs ScalarType: delegates to string-based is_subtype.
        - ParameterizedType vs ParameterizedType: same constructor + all
          arguments pairwise subtypes.
        - ParameterizedType vs ScalarType: child's constructor must be a
          subtype of the parent scalar (e.g. Pointer[Int] ⊆ Pointer ⊆ Any).
        - ScalarType vs ParameterizedType: never (Int is not ⊆ Pointer[X]).
        """
        # Union child: every member must be a subtype of parent
        if isinstance(child, UnionType):
            return all(self.is_subtype_expr(m, parent) for m in child.members)
        # Union parent: child must be subtype of at least one member
        if isinstance(parent, UnionType):
            return any(self.is_subtype_expr(child, m) for m in parent.members)
        match (child, parent):
            case (ScalarType(name=cn), ScalarType(name=pn)):
                return self.is_subtype(cn, pn)
            case (
                ParameterizedType(constructor=cc, arguments=ca),
                ParameterizedType(constructor=pc, arguments=pa),
            ):
                if cc != pc or len(ca) != len(pa):
                    return False
                return all(
                    self.is_subtype_expr(ca_i, pa_i) for ca_i, pa_i in zip(ca, pa)
                )
            case (ParameterizedType(constructor=cc), ScalarType(name=pn)):
                return self.is_subtype(cc, pn)
            case _:
                return False

    def common_supertype_expr(self, type_a: TypeExpr, type_b: TypeExpr) -> TypeExpr:
        """Compute the least upper bound of two TypeExpr values.

        Rules:
        - Union involved: merge all members into a single union.
        - Both scalar: delegates to string-based common_supertype.
        - Both parameterized with same constructor: constructor applied to
          pairwise LUBs of arguments.
        - Otherwise: falls back to scalar Any.
        """
        if type_a == type_b:
            return type_a
        # Union: collect all members and merge
        if isinstance(type_a, UnionType) or isinstance(type_b, UnionType):
            members_a = (
                type_a.members if isinstance(type_a, UnionType) else frozenset({type_a})
            )
            members_b = (
                type_b.members if isinstance(type_b, UnionType) else frozenset({type_b})
            )
            return union_of(*members_a, *members_b)
        match (type_a, type_b):
            case (ScalarType(name=na), ScalarType(name=nb)):
                return scalar(self.common_supertype(na, nb))
            case (
                ParameterizedType(constructor=ca, arguments=aa),
                ParameterizedType(constructor=cb, arguments=ab),
            ):
                if ca != cb or len(aa) != len(ab):
                    return scalar(TypeName.ANY)
                merged_args = tuple(
                    self.common_supertype_expr(aa_i, ab_i) for aa_i, ab_i in zip(aa, ab)
                )
                return ParameterizedType(ca, merged_args)
            case _:
                return scalar(TypeName.ANY)

    def extend(self, additional: tuple[TypeNode, ...]) -> "TypeGraph":
        """Return a new TypeGraph with the additional nodes merged in."""
        merged = self._nodes.copy()
        for node in additional:
            merged[node.name] = node
        return TypeGraph(tuple(merged.values()))
