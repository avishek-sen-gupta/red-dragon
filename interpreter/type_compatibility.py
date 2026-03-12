"""TypeCompatibility — scores how well a runtime arg matches a declared parameter type."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from interpreter.constants import TypeName
from interpreter.type_expr import ScalarType, TypeExpr, UnknownType
from interpreter.vm import runtime_type_name

logger = logging.getLogger(__name__)

# Pairs where coercion is valid (source_type, target_type)
_COMPATIBLE_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        (TypeName.INT, TypeName.FLOAT),
        (TypeName.FLOAT, TypeName.INT),
        (TypeName.BOOL, TypeName.INT),
        (TypeName.BOOL, TypeName.FLOAT),
    }
)


class TypeCompatibility(Protocol):
    """Scores how well a runtime argument matches a declared parameter type."""

    def score(self, arg: Any, declared_type: TypeExpr) -> int:
        """Return compatibility score: 2=exact, 1=compatible, 0=neutral, -1=mismatch."""
        ...


class DefaultTypeCompatibility:
    """Default scoring: exact=2, compatible=1, neutral=0, mismatch=-1.

    Heap addresses (strings starting with "obj_") are scored as neutral
    to avoid false matches with String-typed overloads.
    """

    def score(self, arg: Any, declared_type: TypeExpr) -> int:
        if isinstance(declared_type, UnknownType):
            return 0

        rt = runtime_type_name(arg)

        # Unknown runtime type (symbolic, list, dict, None, etc.)
        if not rt:
            return 0

        # Heap addresses are strings but should not match String params
        if rt == TypeName.STRING and isinstance(arg, str) and arg.startswith("obj_"):
            return 0

        if not isinstance(declared_type, ScalarType):
            return 0

        declared_name = declared_type.name

        if rt == declared_name:
            return 2

        if (rt, declared_name) in _COMPATIBLE_PAIRS:
            return 1

        return -1
