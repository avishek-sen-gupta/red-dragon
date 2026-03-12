"""Unit tests for OverloadResolver -- compositor of strategy + ambiguity handler."""

import pytest

from interpreter.ambiguity_handler import (
    AmbiguousOverloadError,
    FallbackFirstWithWarning,
    StrictAmbiguityHandler,
)
from interpreter.constants import TypeName
from interpreter.function_signature import FunctionSignature
from interpreter.overload_resolver import NullOverloadResolver, OverloadResolver
from interpreter.resolution_strategy import ArityThenTypeStrategy
from interpreter.type_compatibility import DefaultTypeCompatibility
from interpreter.type_expr import scalar, UNKNOWN


def _sig(*param_types: str) -> FunctionSignature:
    return FunctionSignature(
        params=tuple(
            (f"p{i}", scalar(t) if t else UNKNOWN) for i, t in enumerate(param_types)
        ),
        return_type=UNKNOWN,
    )


def _make_resolver(strict: bool = False) -> OverloadResolver:
    compat = DefaultTypeCompatibility()
    strategy = ArityThenTypeStrategy(compat)
    handler = StrictAmbiguityHandler() if strict else FallbackFirstWithWarning()
    return OverloadResolver(strategy, handler)


class TestOverloadResolver:
    # -- Edge cases --

    def test_empty_candidates_returns_zero(self):
        resolver = _make_resolver()
        assert resolver.resolve([], [42]) == 0

    def test_single_candidate_returns_zero(self):
        resolver = _make_resolver()
        assert resolver.resolve([_sig(TypeName.INT)], [42]) == 0

    # -- Arity resolution --

    def test_picks_matching_arity(self):
        resolver = _make_resolver()
        candidates = [_sig(TypeName.INT, TypeName.INT), _sig(TypeName.INT)]
        assert resolver.resolve(candidates, [42]) == 1

    # -- Type resolution --

    def test_picks_matching_type(self):
        resolver = _make_resolver()
        candidates = [_sig(TypeName.STRING), _sig(TypeName.INT)]
        assert resolver.resolve(candidates, [42]) == 1

    # -- Strict handler raises on genuine ambiguity --

    def test_strict_raises_on_identical_signatures(self):
        resolver = _make_resolver(strict=True)
        candidates = [_sig(TypeName.INT), _sig(TypeName.INT)]
        with pytest.raises(AmbiguousOverloadError):
            resolver.resolve(candidates, [42])

    # -- Fallback handler resolves ambiguity silently --

    def test_fallback_resolves_identical_signatures(self):
        resolver = _make_resolver(strict=False)
        candidates = [_sig(TypeName.INT), _sig(TypeName.INT)]
        result = resolver.resolve(candidates, [42])
        assert result in (0, 1)

    # -- End-to-end: multi-arg disambiguation --

    def test_multi_arg_picks_best_type_match(self):
        resolver = _make_resolver()
        candidates = [
            _sig(TypeName.STRING, TypeName.INT),
            _sig(TypeName.INT, TypeName.STRING),
        ]
        assert resolver.resolve(candidates, [42, "hello"]) == 1


class TestNullOverloadResolver:
    def test_always_returns_zero(self):
        resolver = NullOverloadResolver()
        assert resolver.resolve([_sig(TypeName.INT), _sig(TypeName.STRING)], [42]) == 0

    def test_empty_candidates_returns_zero(self):
        resolver = NullOverloadResolver()
        assert resolver.resolve([], []) == 0
