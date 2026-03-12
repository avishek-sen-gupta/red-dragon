"""AmbiguityHandler -- decides what to do when overload resolution is inconclusive."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from interpreter.function_signature import FunctionSignature
from interpreter.vm import runtime_type_name

logger = logging.getLogger(__name__)


class AmbiguousOverloadError(Exception):
    """Raised by StrictAmbiguityHandler when resolution is ambiguous."""


class AmbiguityHandler(Protocol):
    """Pick winner from equally-ranked overload candidates."""

    def handle(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
        ranked: list[int],
    ) -> int:
        """Return index into candidates for the winning overload."""
        ...


class FallbackFirstWithWarning:
    """Default handler: pick first ranked candidate and log a warning."""

    def handle(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
        ranked: list[int],
    ) -> int:
        arg_types = [runtime_type_name(a) or type(a).__name__ for a in args]
        logger.warning(
            "Ambiguous overload resolution: %d candidates for args %s, picking index %d",
            len(candidates),
            arg_types,
            ranked[0],
        )
        return ranked[0]


class StrictAmbiguityHandler:
    """Testing handler: raise on ambiguity to verify resolution is disambiguating."""

    def handle(
        self,
        candidates: list[FunctionSignature],
        args: list[Any],
        ranked: list[int],
    ) -> int:
        arg_types = [runtime_type_name(a) or type(a).__name__ for a in args]
        raise AmbiguousOverloadError(
            f"Ambiguous overload: {len(candidates)} candidates for args {arg_types}"
        )
