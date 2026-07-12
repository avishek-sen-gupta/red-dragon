# pyright: standard
"""TypeGraph — DAG of types with subtype queries and least-upper-bound."""

from __future__ import annotations

import logging
from collections import deque

from interpreter.constants import FoundationTypeName, Variance
from interpreter.type_name import TypeName
from interpreter.types.type_expr import (
    FunctionType,
    ParameterizedType,
    ScalarType,
    TypeExpr,
    TypeVar,
    UnionType,
    scalar,
    union_of,
)
from interpreter.types.type_node import TypeNode

logger = logging.getLogger(__name__)


DEFAULT_TYPE_NODES: tuple[TypeNode, ...] = (
    TypeNode(name=FoundationTypeName.ANY, parents=()),
    TypeNode(name=FoundationTypeName.NUMBER, parents=(FoundationTypeName.ANY,)),
    TypeNode(name=FoundationTypeName.STRING, parents=(FoundationTypeName.ANY,)),
    TypeNode(name=FoundationTypeName.BOOL, parents=(FoundationTypeName.ANY,)),
    TypeNode(name=FoundationTypeName.OBJECT, parents=(FoundationTypeName.ANY,)),
    TypeNode(name=FoundationTypeName.ARRAY, parents=(FoundationTypeName.ANY,)),
    TypeNode(name=FoundationTypeName.INT, parents=(FoundationTypeName.NUMBER,)),
    TypeNode(name=FoundationTypeName.FLOAT, parents=(FoundationTypeName.NUMBER,)),
    TypeNode(name=FoundationTypeName.POINTER, parents=(FoundationTypeName.ANY,)),
    TypeNode(name=FoundationTypeName.MAP, parents=(FoundationTypeName.ANY,)),
    TypeNode(name=FoundationTypeName.TUPLE, parents=(FoundationTypeName.ANY,)),
    TypeNode(name=FoundationTypeName.REGION, parents=(FoundationTypeName.ANY,)),
)


class TypeGraph:
    """Immutable DAG of types supporting subtype checks and LUB queries.

    Constructed from a tuple of TypeNode values. Use extend() to produce
    a new graph with additional nodes without mutating the original.

    ``variance_registry`` maps constructor names to per-argument variance:
    e.g. ``{"MutableList": (Variance.INVARIANT,)}``.  Unlisted constructors
    default to all-covariant.
    """

    def __init__(
        self,
        nodes: tuple[TypeNode, ...],
        variance_registry: dict[str, tuple[Variance, ...]] = {},
    ) -> None:
        self._nodes: dict[TypeName, TypeNode] = {node.name: node for node in nodes}
        self._variance_registry = variance_registry

    def contains(self, type_name: TypeName) -> bool:
        return type_name in self._nodes

    def is_subtype(self, child: TypeName, parent: TypeName) -> bool:
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

    def _ancestors(self, type_name: TypeName) -> list[TypeName]:
        """Return all ancestors of type_name in BFS order, including itself."""
        result: list[TypeName] = []
        visited: set[TypeName] = set()
        queue: deque[TypeName] = deque([type_name])
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

    def common_supertype(self, type_a: TypeName, type_b: TypeName) -> TypeName:
        """Return the least upper bound (closest common ancestor) of two types.

        Returns FoundationTypeName.ANY for unknown types.
        """
        if type_a == type_b:
            return type_a
        if type_a not in self._nodes or type_b not in self._nodes:
            return FoundationTypeName.ANY
        ancestors_a = self._ancestors(type_a)
        ancestors_b_set = set(self._ancestors(type_b))
        common = [a for a in ancestors_a if a in ancestors_b_set]
        return common[0] if common else FoundationTypeName.ANY

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
        # TypeVar child: subtype if bound is subtype of parent
        if isinstance(child, TypeVar):
            bound = child.bound if child.bound else scalar(FoundationTypeName.ANY)
            return self.is_subtype_expr(bound, parent)
        # TypeVar parent: child satisfies it if child is subtype of the bound
        if isinstance(parent, TypeVar):
            bound = parent.bound if parent.bound else scalar(FoundationTypeName.ANY)
            return self.is_subtype_expr(child, bound)
        match (child, parent):
            case (ScalarType(name=cn), ScalarType(name=pn)):
                return self.is_subtype(cn, pn)
            case (
                ParameterizedType(constructor=cc, arguments=ca),
                ParameterizedType(constructor=pc, arguments=pa),
            ):
                if cc != pc or len(ca) != len(pa):
                    return False
                variances = self._variance_registry.get(cc, ())
                return all(
                    self._check_variance(
                        ca_i,
                        pa_i,
                        variances[i] if i < len(variances) else Variance.COVARIANT,
                    )
                    for i, (ca_i, pa_i) in enumerate(zip(ca, pa))
                )
            case (ParameterizedType(constructor=cc), ScalarType(name=pn)):
                return self.is_subtype(TypeName(cc), pn)
            case (
                FunctionType(params=cp, return_type=cr),
                FunctionType(params=pp, return_type=pr),
            ):
                if len(cp) != len(pp):
                    return False
                # Contravariant params: parent param must be subtype of child param
                params_ok = all(
                    self.is_subtype_expr(pp_i, cp_i) for cp_i, pp_i in zip(cp, pp)
                )
                # Covariant return: child return must be subtype of parent return
                return params_ok and self.is_subtype_expr(cr, pr)
            case _:
                return False

    def _lub_with_variance(
        self, a: TypeExpr, b: TypeExpr, variance: Variance
    ) -> TypeExpr:
        """Compute LUB for a single type argument according to its variance."""
        if variance == Variance.INVARIANT:
            # Invariant: must be exactly equal
            return a if a == b else scalar(FoundationTypeName.ANY)
        # Covariant and contravariant both use the standard LUB
        return self.common_supertype_expr(a, b)

    def _check_variance(
        self, child_arg: TypeExpr, parent_arg: TypeExpr, variance: Variance
    ) -> bool:
        """Check a single type argument pair according to its variance."""
        if variance == Variance.COVARIANT:
            return self.is_subtype_expr(child_arg, parent_arg)
        if variance == Variance.CONTRAVARIANT:
            return self.is_subtype_expr(parent_arg, child_arg)
        # INVARIANT: must be exactly equal
        return child_arg == parent_arg

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
                    return scalar(FoundationTypeName.ANY)
                variances = self._variance_registry.get(ca, ())
                merged_args = tuple(
                    self._lub_with_variance(
                        aa_i,
                        ab_i,
                        variances[i] if i < len(variances) else Variance.COVARIANT,
                    )
                    for i, (aa_i, ab_i) in enumerate(zip(aa, ab))
                )
                # If any invariant argument couldn't match, fall back to Any
                if any(a == scalar(FoundationTypeName.ANY) for a in merged_args):
                    inv_positions = [
                        i
                        for i in range(len(merged_args))
                        if i < len(variances)
                        and variances[i] == Variance.INVARIANT
                        and aa[i] != ab[i]
                    ]
                    if inv_positions:
                        return scalar(FoundationTypeName.ANY)
                return ParameterizedType(ca, merged_args)
            case (
                FunctionType(params=pa, return_type=ra),
                FunctionType(params=pb, return_type=rb),
            ):
                if len(pa) != len(pb):
                    return scalar(FoundationTypeName.ANY)
                merged_params = tuple(
                    self.common_supertype_expr(pa_i, pb_i) for pa_i, pb_i in zip(pa, pb)
                )
                merged_return = self.common_supertype_expr(ra, rb)
                return FunctionType(params=merged_params, return_type=merged_return)
            case _:
                return scalar(FoundationTypeName.ANY)

    def extend(self, additional: tuple[TypeNode, ...]) -> TypeGraph:
        """Return a new TypeGraph with the additional nodes merged in."""
        merged = self._nodes.copy()
        for node in additional:
            merged[node.name] = node
        return TypeGraph(tuple(merged.values()), self._variance_registry)

    def extend_with_interfaces(
        self, implementations: dict[str, tuple[str, ...]]
    ) -> TypeGraph:
        """Return a new TypeGraph with class→interface edges added.

        For each ``class_name → (iface1, iface2, ...)``, adds interface
        nodes (if missing) and a class node with those interfaces as parents.
        Existing parents are preserved.
        """
        merged = self._nodes.copy()
        for class_name, interfaces in implementations.items():
            cls_key = TypeName(class_name)
            iface_keys = tuple(TypeName(i) for i in interfaces)
            for iface_key in iface_keys:
                if iface_key not in merged:
                    merged[iface_key] = TypeNode(
                        name=iface_key,
                        parents=(FoundationTypeName.ANY,),
                        kind="interface",
                    )
            existing = merged.get(cls_key)
            existing_parents = existing.parents if existing else ()
            all_parents = tuple(
                dict.fromkeys(list(existing_parents) + list(iface_keys))
            )
            merged[cls_key] = TypeNode(name=cls_key, parents=all_parents)
        return TypeGraph(tuple(merged.values()), self._variance_registry)

    def with_variance(
        self, variance_registry: dict[str, tuple[Variance, ...]]
    ) -> TypeGraph:
        """Return a new TypeGraph with the given variance annotations."""
        merged = dict(self._variance_registry)
        merged.update(variance_registry)
        return TypeGraph(tuple(self._nodes.values()), merged)
