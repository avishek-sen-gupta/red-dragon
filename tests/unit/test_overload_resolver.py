"""Unit tests for OverloadResolver -- compositor of strategy + ambiguity handler."""

import pytest

from interpreter.constants import FoundationTypeName
from interpreter.overload.ambiguity_handler import (
    AmbiguousOverloadError,
    FallbackFirstWithWarning,
    StrictAmbiguityHandler,
)
from interpreter.overload.overload_resolver import (
    NullOverloadResolver,
    OverloadResolver,
)
from interpreter.overload.resolution_strategy import ArityThenTypeStrategy
from interpreter.type_name import TypeName
from interpreter.types.coercion.type_compatibility import DefaultTypeCompatibility
from interpreter.types.function_signature import FunctionSignature
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.type_graph import DEFAULT_TYPE_NODES, TypeGraph
from interpreter.types.type_node import TypeNode
from interpreter.types.typed_value import typed


def _sig(*param_types: TypeName | str) -> FunctionSignature:
    return FunctionSignature(
        params=tuple(
            (
                f"p{i}",
                scalar(t if isinstance(t, TypeName) else TypeName(t)) if t else UNKNOWN,
            )
            for i, t in enumerate(param_types)
        ),
        return_type=UNKNOWN,
    )


def _make_resolver(strict: bool = False) -> OverloadResolver:
    type_graph = TypeGraph(DEFAULT_TYPE_NODES)
    compat = DefaultTypeCompatibility(type_graph)
    strategy = ArityThenTypeStrategy(compat)
    handler = StrictAmbiguityHandler() if strict else FallbackFirstWithWarning()
    return OverloadResolver(strategy, handler)


class TestOverloadResolver:
    # -- Edge cases --

    def test_empty_candidates_returns_zero(self):
        resolver = _make_resolver()
        assert resolver.resolve([], [typed(42, scalar(FoundationTypeName.INT))]) == 0

    def test_single_candidate_returns_zero(self):
        resolver = _make_resolver()
        assert (
            resolver.resolve(
                [_sig(FoundationTypeName.INT)],
                [typed(42, scalar(FoundationTypeName.INT))],
            )
            == 0
        )

    # -- Arity resolution --

    def test_picks_matching_arity(self):
        resolver = _make_resolver()
        candidates = [
            _sig(FoundationTypeName.INT, FoundationTypeName.INT),
            _sig(FoundationTypeName.INT),
        ]
        assert (
            resolver.resolve(candidates, [typed(42, scalar(FoundationTypeName.INT))])
            == 1
        )

    # -- Type resolution --

    def test_picks_matching_type(self):
        resolver = _make_resolver()
        candidates = [_sig(FoundationTypeName.STRING), _sig(FoundationTypeName.INT)]
        assert (
            resolver.resolve(candidates, [typed(42, scalar(FoundationTypeName.INT))])
            == 1
        )

    # -- Strict handler raises on genuine ambiguity --

    def test_strict_raises_on_identical_signatures(self):
        resolver = _make_resolver(strict=True)
        candidates = [_sig(FoundationTypeName.INT), _sig(FoundationTypeName.INT)]
        with pytest.raises(AmbiguousOverloadError):
            resolver.resolve(candidates, [typed(42, scalar(FoundationTypeName.INT))])

    # -- Fallback handler resolves ambiguity silently --

    def test_fallback_resolves_identical_signatures(self):
        resolver = _make_resolver(strict=False)
        candidates = [_sig(FoundationTypeName.INT), _sig(FoundationTypeName.INT)]
        result = resolver.resolve(
            candidates, [typed(42, scalar(FoundationTypeName.INT))]
        )
        assert result in (0, 1)

    # -- End-to-end: multi-arg disambiguation --

    def test_multi_arg_picks_best_type_match(self):
        resolver = _make_resolver()
        candidates = [
            _sig(FoundationTypeName.STRING, FoundationTypeName.INT),
            _sig(FoundationTypeName.INT, FoundationTypeName.STRING),
        ]
        assert (
            resolver.resolve(
                candidates,
                [
                    typed(42, scalar(FoundationTypeName.INT)),
                    typed("hello", scalar(FoundationTypeName.STRING)),
                ],
            )
            == 1
        )


class TestNullOverloadResolver:
    def test_always_returns_zero(self):
        resolver = NullOverloadResolver()
        assert (
            resolver.resolve(
                [_sig(FoundationTypeName.INT), _sig(FoundationTypeName.STRING)],
                [typed(42, scalar(FoundationTypeName.INT))],
            )
            == 0
        )

    def test_empty_candidates_returns_zero(self):
        resolver = NullOverloadResolver()
        assert resolver.resolve([], []) == 0


def _make_resolver_with_classes(strict: bool = False) -> OverloadResolver:
    class_nodes = (
        TypeNode(name=TypeName("Animal"), parents=(TypeName("Any"),)),
        TypeNode(name=TypeName("Dog"), parents=(TypeName("Animal"),)),
        TypeNode(name=TypeName("Cat"), parents=(TypeName("Animal"),)),
    )
    type_graph = TypeGraph(DEFAULT_TYPE_NODES + class_nodes)
    compat = DefaultTypeCompatibility(type_graph)
    strategy = ArityThenTypeStrategy(compat)
    handler = StrictAmbiguityHandler() if strict else FallbackFirstWithWarning()
    return OverloadResolver(strategy, handler)


class TestSubtypeOverloadResolution:
    def test_picks_exact_class_over_parent(self):
        """foo(Dog) should beat foo(Animal) when passing a Dog."""
        resolver = _make_resolver_with_classes()
        candidates = [_sig("Animal"), _sig("Dog")]
        assert (
            resolver.resolve(candidates, [typed("obj_0", scalar(TypeName("Dog")))]) == 1
        )

    def test_picks_parent_when_no_exact(self):
        """foo(Animal) should match when passing a Dog and no foo(Dog) exists."""
        resolver = _make_resolver_with_classes()
        candidates = [_sig(FoundationTypeName.STRING), _sig("Animal")]
        assert (
            resolver.resolve(candidates, [typed("obj_0", scalar(TypeName("Dog")))]) == 1
        )

    def test_sibling_class_exact_match_beats_mismatch(self):
        """foo(Dog) and foo(Cat) with a Dog arg — Dog matches exactly, Cat mismatches."""
        resolver = _make_resolver_with_classes()
        candidates = [_sig("Cat"), _sig("Dog")]
        assert (
            resolver.resolve(candidates, [typed("obj_0", scalar(TypeName("Dog")))]) == 1
        )
