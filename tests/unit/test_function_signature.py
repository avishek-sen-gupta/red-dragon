"""Tests for FunctionSignature kind classification and callable_params."""

from __future__ import annotations
from interpreter.type_name import TypeName

from interpreter.types.function_kind import FunctionKind
from interpreter.types.function_signature import FunctionSignature
from interpreter.types.type_expr import scalar


class TestFunctionKindDefault:
    """FunctionSignature defaults to UNBOUND."""

    def test_default_kind_is_unbound(self):
        sig = FunctionSignature(params=(), return_type=scalar(TypeName("Int")))
        assert sig.kind is FunctionKind.UNBOUND

    def test_explicit_instance_kind(self):
        sig = FunctionSignature(
            params=(("this", scalar(TypeName("Dog"))),),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.INSTANCE,
        )
        assert sig.kind is FunctionKind.INSTANCE

    def test_explicit_static_kind(self):
        sig = FunctionSignature(
            params=(("a", scalar(TypeName("Int"))),),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.STATIC,
        )
        assert sig.kind is FunctionKind.STATIC


class TestCallableParams:
    """callable_params excludes this/$this only for INSTANCE methods."""

    def test_unbound_returns_all_params(self):
        sig = FunctionSignature(
            params=(("a", scalar(TypeName("Int"))), ("b", scalar(TypeName("Int")))),
            return_type=scalar(TypeName("Int")),
        )
        assert sig.callable_params == (
            ("a", scalar(TypeName("Int"))),
            ("b", scalar(TypeName("Int"))),
        )

    def test_static_returns_all_params(self):
        sig = FunctionSignature(
            params=(("a", scalar(TypeName("Int"))),),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.STATIC,
        )
        assert sig.callable_params == (("a", scalar(TypeName("Int"))),)

    def test_instance_excludes_this(self):
        sig = FunctionSignature(
            params=(
                ("this", scalar(TypeName("Dog"))),
                ("name", scalar(TypeName("String"))),
            ),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.INSTANCE,
        )
        assert sig.callable_params == (("name", scalar(TypeName("String"))),)

    def test_instance_excludes_dollar_this(self):
        sig = FunctionSignature(
            params=(
                ("$this", scalar(TypeName("User"))),
                ("msg", scalar(TypeName("String"))),
            ),
            return_type=scalar(TypeName("String")),
            kind=FunctionKind.INSTANCE,
        )
        assert sig.callable_params == (("msg", scalar(TypeName("String"))),)

    def test_instance_with_only_this_returns_empty(self):
        sig = FunctionSignature(
            params=(("this", scalar(TypeName("Dog"))),),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.INSTANCE,
        )
        assert sig.callable_params == ()

    def test_instance_without_this_param_returns_all(self):
        """Edge case: INSTANCE kind but no this param — returns all params."""
        sig = FunctionSignature(
            params=(("a", scalar(TypeName("Int"))),),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.INSTANCE,
        )
        assert sig.callable_params == (("a", scalar(TypeName("Int"))),)


class TestFunctionKindEquality:
    """Kind field participates in frozen dataclass equality."""

    def test_same_params_different_kind_not_equal(self):
        instance = FunctionSignature(
            params=(("this", scalar(TypeName("Dog"))),),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.INSTANCE,
        )
        static = FunctionSignature(
            params=(("this", scalar(TypeName("Dog"))),),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.STATIC,
        )
        assert instance != static

    def test_same_kind_same_params_equal(self):
        a = FunctionSignature(
            params=(("x", scalar(TypeName("Int"))),),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.STATIC,
        )
        b = FunctionSignature(
            params=(("x", scalar(TypeName("Int"))),),
            return_type=scalar(TypeName("Int")),
            kind=FunctionKind.STATIC,
        )
        assert a == b
