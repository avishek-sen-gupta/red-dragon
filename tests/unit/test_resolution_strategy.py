"""Unit tests for ResolutionStrategy — candidate ranking by arity then type."""

from interpreter.constants import TypeName
from interpreter.function_kind import FunctionKind
from interpreter.function_signature import FunctionSignature
from interpreter.resolution_strategy import ArityThenTypeStrategy
from interpreter.type_compatibility import DefaultTypeCompatibility
from interpreter.type_expr import scalar, UNKNOWN


def _sig(
    *param_types: str, kind: FunctionKind = FunctionKind.UNBOUND
) -> FunctionSignature:
    """Helper: create FunctionSignature from TypeName strings."""
    return FunctionSignature(
        params=tuple(
            (f"p{i}", scalar(t) if t else UNKNOWN) for i, t in enumerate(param_types)
        ),
        return_type=UNKNOWN,
        kind=kind,
    )


def _instance_sig(*param_types: str) -> FunctionSignature:
    """Helper: instance method with 'this' as first param + given params."""
    params = [("this", UNKNOWN)] + [
        (f"p{i}", scalar(t) if t else UNKNOWN) for i, t in enumerate(param_types)
    ]
    return FunctionSignature(
        params=tuple(params),
        return_type=UNKNOWN,
        kind=FunctionKind.INSTANCE,
    )


class TestArityThenTypeStrategy:
    def setup_method(self):
        self.strategy = ArityThenTypeStrategy(DefaultTypeCompatibility())

    # -- Arity-based resolution --

    def test_single_candidate_returns_it(self):
        candidates = [_sig(TypeName.INT)]
        assert self.strategy.rank(candidates, [42]) == [0]

    def test_empty_candidates_returns_empty(self):
        assert self.strategy.rank([], [42]) == []

    def test_arity_match_preferred(self):
        candidates = [_sig(TypeName.INT, TypeName.INT), _sig(TypeName.INT)]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 1

    def test_two_args_picks_two_param_overload(self):
        candidates = [_sig(TypeName.INT), _sig(TypeName.INT, TypeName.STRING)]
        ranked = self.strategy.rank(candidates, [42, "hello"])
        assert ranked[0] == 1

    def test_zero_args_picks_nullary(self):
        candidates = [_sig(TypeName.INT), _sig()]
        ranked = self.strategy.rank(candidates, [])
        assert ranked[0] == 1

    def test_fewer_args_than_params_scores_by_available(self):
        """2 args against a 3-param candidate — only first 2 positions scored."""
        candidates = [
            _sig(TypeName.INT, TypeName.STRING, TypeName.FLOAT),
            _sig(TypeName.INT, TypeName.STRING),
        ]
        ranked = self.strategy.rank(candidates, [42, "hello"])
        assert ranked[0] == 1  # exact arity match wins

    # -- Type-based tiebreaking --

    def test_same_arity_exact_type_wins(self):
        candidates = [_sig(TypeName.STRING), _sig(TypeName.INT)]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 1

    def test_same_arity_compatible_vs_mismatch(self):
        candidates = [_sig(TypeName.STRING), _sig(TypeName.FLOAT)]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 1

    def test_same_arity_both_exact_preserves_order(self):
        candidates = [_sig(TypeName.INT), _sig(TypeName.INT)]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 0

    # -- Instance methods use callable_params (excludes this) --

    def test_instance_method_arity_excludes_this(self):
        candidates = [
            _instance_sig(TypeName.INT, TypeName.INT),
            _instance_sig(TypeName.INT),
        ]
        ranked = self.strategy.rank(candidates, [42])
        assert ranked[0] == 1

    # -- Multi-argument type scoring --

    def test_multi_arg_type_score_sum(self):
        candidates = [
            _sig(TypeName.STRING, TypeName.INT),
            _sig(TypeName.INT, TypeName.STRING),
        ]
        ranked = self.strategy.rank(candidates, [42, "hello"])
        assert ranked[0] == 1

    # -- Unknown types are neutral --

    def test_unknown_args_dont_penalize(self):
        candidates = [_sig(TypeName.INT), _sig(TypeName.STRING)]
        ranked = self.strategy.rank(candidates, ["obj_Dog_0"])
        assert ranked[0] == 0
