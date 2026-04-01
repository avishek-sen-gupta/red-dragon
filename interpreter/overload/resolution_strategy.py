# pyright: standard
"""ResolutionStrategy — ranks overload candidates by arity then type compatibility."""

from __future__ import annotations

import logging
from typing import Protocol

from interpreter.types.function_signature import FunctionSignature
from interpreter.types.coercion.type_compatibility import TypeCompatibility
from interpreter.types.typed_value import TypedValue

logger = logging.getLogger(__name__)


class ResolutionStrategy(Protocol):
    """Ranks overload candidates from best to worst match."""

    def rank(
        self,
        candidates: list[FunctionSignature],
        args: list[TypedValue],
    ) -> list[int]:
        """Return candidate indices sorted best-to-worst."""
        ...


class ArityThenTypeStrategy:
    """Default strategy: filter by arity distance, then rank by type score."""

    def __init__(self, type_compatibility: TypeCompatibility) -> None:
        self._type_compatibility = type_compatibility

    def rank(
        self,
        candidates: list[FunctionSignature],
        args: list[TypedValue],
    ) -> list[int]:
        if not candidates:
            return []

        # Score each candidate: (arity_distance, -type_score, original_index)
        scored = [
            (self._arity_distance(sig, args), -self._type_score(sig, args), i)
            for i, sig in enumerate(candidates)
        ]
        scored.sort()
        return [i for _, _, i in scored]

    def _arity_distance(self, sig: FunctionSignature, args: list[TypedValue]) -> int:
        return abs(len(sig.callable_params) - len(args))

    def _type_score(self, sig: FunctionSignature, args: list[TypedValue]) -> int:
        params = sig.callable_params
        return sum(
            self._type_compatibility.score(arg, param_type)
            for arg, (_, param_type) in zip(args, params)
        )
