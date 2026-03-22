"""Unit tests for AmbiguityHandler implementations."""

import logging

import pytest

from interpreter.overload.ambiguity_handler import (
    AmbiguousOverloadError,
    FallbackFirstWithWarning,
    StrictAmbiguityHandler,
)
from interpreter.types.function_signature import FunctionSignature
from interpreter.types.type_expr import UNKNOWN
from interpreter.types.typed_value import typed


def _sig(n_params: int) -> FunctionSignature:
    """Helper: create a FunctionSignature with n_params UNKNOWN-typed params."""
    return FunctionSignature(
        params=tuple((f"p{i}", UNKNOWN) for i in range(n_params)),
        return_type=UNKNOWN,
    )


class TestFallbackFirstWithWarning:
    def test_returns_first_ranked(self):
        handler = FallbackFirstWithWarning()
        candidates = [_sig(1), _sig(2), _sig(3)]
        result = handler.handle(candidates, [typed(42, UNKNOWN)], [2, 0, 1])
        assert result == 2

    def test_logs_warning(self, caplog):
        handler = FallbackFirstWithWarning()
        candidates = [_sig(1), _sig(2)]
        with caplog.at_level(logging.WARNING):
            handler.handle(
                candidates, [typed(42, UNKNOWN), typed("hello", UNKNOWN)], [0, 1]
            )
        assert "ambiguous" in caplog.text.lower()

    def test_single_ranked_returns_it(self):
        handler = FallbackFirstWithWarning()
        candidates = [_sig(1)]
        result = handler.handle(candidates, [typed(42, UNKNOWN)], [0])
        assert result == 0


class TestStrictAmbiguityHandler:
    def test_raises_on_ambiguity(self):
        handler = StrictAmbiguityHandler()
        candidates = [_sig(1), _sig(2)]
        with pytest.raises(AmbiguousOverloadError):
            handler.handle(candidates, [typed(42, UNKNOWN)], [0, 1])

    def test_error_contains_candidate_count(self):
        handler = StrictAmbiguityHandler()
        candidates = [_sig(1), _sig(2), _sig(3)]
        with pytest.raises(AmbiguousOverloadError, match="3"):
            handler.handle(candidates, [typed(42, UNKNOWN)], [0, 1, 2])
