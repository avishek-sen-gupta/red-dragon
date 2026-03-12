"""Unit tests for TypeEnvironmentBuilder."""

from types import MappingProxyType

from interpreter.function_signature import FunctionSignature
from interpreter.type_environment_builder import TypeEnvironmentBuilder
from interpreter.type_expr import (
    TypeExpr,
    ScalarType,
    ParameterizedType,
    UNBOUND,
    UNKNOWN,
    parse_type,
    scalar,
)


class TestTypeEnvironmentBuilder:
    def test_build_empty_produces_empty_type_environment(self):
        builder = TypeEnvironmentBuilder()
        env = builder.build()
        assert dict(env.register_types) == {}
        assert dict(env.var_types) == {}
        assert dict(env.method_signatures) == {}

    def test_build_preserves_register_types(self):
        builder = TypeEnvironmentBuilder(
            register_types={"%0": scalar("Int"), "%1": scalar("Float")}
        )
        env = builder.build()
        assert env.register_types["%0"] == "Int"
        assert env.register_types["%1"] == "Float"

    def test_build_preserves_var_types(self):
        builder = TypeEnvironmentBuilder(
            var_types={"x": scalar("Int"), "name": scalar("String")}
        )
        env = builder.build()
        assert env.var_types["x"] == "Int"
        assert env.var_types["name"] == "String"

    def test_build_creates_func_signatures_from_return_and_param_types(self):
        builder = TypeEnvironmentBuilder(
            func_return_types={"add": scalar("Int")},
            func_param_types={"add": [("a", scalar("Int")), ("b", scalar("Int"))]},
        )
        env = builder.build()
        unbound_sigs = env.method_signatures.get(UNBOUND, {})
        assert "add" in unbound_sigs
        sig = env.get_func_signature("add")
        assert sig.return_type == "Int"
        assert sig.params == (("a", scalar("Int")), ("b", scalar("Int")))

    def test_build_excludes_internal_func_labels(self):
        builder = TypeEnvironmentBuilder(
            func_return_types={
                "func_add_0": scalar("Int"),
                "add": scalar("Int"),
            },
            func_param_types={
                "func_add_0": [("a", scalar("Int"))],
                "add": [("a", scalar("Int"))],
            },
        )
        env = builder.build()
        unbound_sigs = env.method_signatures.get(UNBOUND, {})
        assert "add" in unbound_sigs
        assert "func_add_0" not in unbound_sigs

    def test_build_returns_frozen_mappings(self):
        builder = TypeEnvironmentBuilder(
            register_types={"%0": scalar("Int")},
            var_types={"x": scalar("Int")},
        )
        env = builder.build()
        assert isinstance(env.register_types, MappingProxyType)
        assert isinstance(env.var_types, MappingProxyType)
        assert isinstance(env.method_signatures, MappingProxyType)

    def test_build_does_not_mutate_builder(self):
        builder = TypeEnvironmentBuilder(
            register_types={"%0": scalar("Int")},
        )
        env = builder.build()
        builder.register_types["%1"] = scalar("Float")
        assert "%1" not in env.register_types

    def test_func_signature_with_return_only(self):
        builder = TypeEnvironmentBuilder(func_return_types={"greet": scalar("String")})
        env = builder.build()
        sig = env.get_func_signature("greet")
        assert sig.return_type == "String"
        assert sig.params == ()

    def test_func_signature_with_params_only(self):
        builder = TypeEnvironmentBuilder(
            func_param_types={"add": [("a", scalar("Int")), ("b", scalar("Int"))]}
        )
        env = builder.build()
        sig = env.get_func_signature("add")
        assert sig.return_type == UNKNOWN
        assert sig.params == (("a", scalar("Int")), ("b", scalar("Int")))


class TestTypeEnvironmentStoresTypeExpr:
    """Verify that TypeEnvironment stores TypeExpr objects, not raw strings."""

    def test_register_types_are_type_expr(self):
        builder = TypeEnvironmentBuilder(register_types={"%0": scalar("Int")})
        env = builder.build()
        assert isinstance(env.register_types["%0"], TypeExpr)
        assert isinstance(env.register_types["%0"], ScalarType)

    def test_var_types_are_type_expr(self):
        builder = TypeEnvironmentBuilder(var_types={"x": scalar("Float")})
        env = builder.build()
        assert isinstance(env.var_types["x"], TypeExpr)
        assert isinstance(env.var_types["x"], ScalarType)

    def test_parameterized_type_preserved(self):
        builder = TypeEnvironmentBuilder(var_types={"ptr": parse_type("Pointer[Int]")})
        env = builder.build()
        assert isinstance(env.var_types["ptr"], ParameterizedType)
        assert env.var_types["ptr"].constructor == "Pointer"
        assert env.var_types["ptr"].arguments == (ScalarType("Int"),)

    def test_func_signature_return_type_is_type_expr(self):
        builder = TypeEnvironmentBuilder(func_return_types={"add": scalar("Int")})
        env = builder.build()
        assert isinstance(env.get_func_signature("add").return_type, TypeExpr)

    def test_func_signature_param_types_are_type_expr(self):
        builder = TypeEnvironmentBuilder(
            func_param_types={
                "f": [("x", scalar("Int")), ("p", parse_type("Pointer[Float]"))]
            }
        )
        env = builder.build()
        sig = env.get_func_signature("f")
        assert isinstance(sig.params[0][1], TypeExpr)
        assert isinstance(sig.params[1][1], ParameterizedType)
        assert sig.params[1][1] == "Pointer[Float]"

    def test_string_comparison_still_works(self):
        """Backward compat: env.register_types['%0'] == 'Int' must hold."""
        builder = TypeEnvironmentBuilder(
            register_types={"%0": scalar("Int")},
            var_types={"x": parse_type("Pointer[Int]")},
        )
        env = builder.build()
        assert env.register_types["%0"] == "Int"
        assert env.var_types["x"] == "Pointer[Int]"
