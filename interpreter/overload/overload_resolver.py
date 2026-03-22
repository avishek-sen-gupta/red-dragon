"""OverloadResolver -- composes ResolutionStrategy and AmbiguityHandler."""

from __future__ import annotations

import logging
from interpreter.types.typed_value import TypedValue

from interpreter.overload.ambiguity_handler import AmbiguityHandler
from interpreter.types.function_signature import FunctionSignature
from interpreter.overload.resolution_strategy import ResolutionStrategy

logger = logging.getLogger(__name__)


class OverloadResolver:
    """Picks the best overload candidate by composing a ranking strategy
    with an ambiguity handler for ties.
    """

    def __init__(
        self,
        strategy: ResolutionStrategy,
        ambiguity_handler: AmbiguityHandler,
    ) -> None:
        self._strategy = strategy
        self._ambiguity_handler = ambiguity_handler

    def resolve(
        self,
        candidates: list[FunctionSignature],
        args: list[TypedValue],
    ) -> int:
        """Return index of winning candidate."""
        if len(candidates) <= 1:
            return 0
        ranked = self._strategy.rank(candidates, args)
        if len(ranked) <= 1:
            return ranked[0]
        return self._ambiguity_handler.handle(candidates, args, ranked)


class NullOverloadResolver(OverloadResolver):
    """Null-object resolver that always returns index 0 (current behavior).

    Used as default parameter value to avoid None checks.
    """

    def __init__(self) -> None:
        pass  # No strategy or handler needed

    def resolve(
        self,
        candidates: list[FunctionSignature],
        args: list[TypedValue],
    ) -> int:
        return 0
