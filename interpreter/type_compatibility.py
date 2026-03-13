"""TypeCompatibility — scores how well a runtime arg matches a declared parameter type."""

from __future__ import annotations

import logging
from typing import Protocol

from interpreter.constants import TypeName
from interpreter.type_expr import ScalarType, TypeExpr, UnknownType
from interpreter.type_graph import TypeGraph
from interpreter.typed_value import TypedValue

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

    def score(self, arg: TypedValue, declared_type: TypeExpr) -> int:
        """Return compatibility score: 2=exact, 1=compatible, 0=neutral, -1=mismatch."""
        ...


class DefaultTypeCompatibility:
    """Default scoring: exact=2, coercion/subtype=1, neutral=0, mismatch=-1.

    Uses _COMPATIBLE_PAIRS for primitive coercion (Int↔Float, Bool→Int)
    and TypeGraph.is_subtype_expr() for class hierarchy subtyping (Dog→Animal).
    """

    def __init__(self, type_graph: TypeGraph) -> None:
        self._type_graph = type_graph

    def score(self, arg: TypedValue, declared_type: TypeExpr) -> int:
        if isinstance(declared_type, UnknownType):
            return 0

        arg_type = arg.type
        if isinstance(arg_type, UnknownType):
            return 0

        if not isinstance(declared_type, ScalarType):
            return 0

        # Exact match
        if isinstance(arg_type, ScalarType) and arg_type.name == declared_type.name:
            return 2

        # Coercion match (Int↔Float, Bool→Int, Bool→Float)
        if (
            isinstance(arg_type, ScalarType)
            and (arg_type.name, declared_type.name) in _COMPATIBLE_PAIRS
        ):
            return 1

        # Subtype match (Dog → Animal, etc.)
        if self._type_graph.is_subtype_expr(arg_type, declared_type):
            return 1

        return -1
