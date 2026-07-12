"""Unit tests for TypeEnvironmentBuilder."""

from types import MappingProxyType

from interpreter.func_name import FuncName
from interpreter.register import Register
from interpreter.type_name import TypeName
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter.types.type_expr import (
    UNBOUND,
    UNKNOWN,
    ParameterizedType,
    ScalarType,
    TypeExpr,
    parse_type,
    scalar,
)
from interpreter.var_name import VarName


class TestTypeEnvironmentBuilder:
    def test_build_empty_produces_empty_type_environment(self):
        builder = TypeEnvironmentBuilder()
        env = builder.build()
        assert dict(env.register_types) == {}
        assert dict(env.var_types) == {}
        assert dict(env.method_signatures) == {}

    def test_build_preserves_register_types(self):
        builder = TypeEnvironmentBuilder(
            register_types={
                Register("%0"): scalar(TypeName("Int")),
                Register("%1"): scalar(TypeName("Float")),
            }
        )
        env = builder.build()
        assert env.register_types[Register("%0")] == "Int"
        assert env.register_types[Register("%1")] == "Float"

    def test_build_preserves_var_types(self):
        builder = TypeEnvironmentBuilder(
            var_types={"x": scalar(TypeName("Int")), "name": scalar(TypeName("String"))}
        )
        env = builder.build()
        assert env.var_types[VarName("x")] == "Int"
        assert env.var_types[VarName("name")] == "String"

    def test_build_creates_func_signatures_from_return_and_param_types(self):
        builder = TypeEnvironmentBuilder(
            func_return_types={"add": scalar(TypeName("Int"))},
            func_param_types={
                "add": [("a", scalar(TypeName("Int"))), ("b", scalar(TypeName("Int")))]
            },
        )
        env = builder.build()
        unbound_sigs = env.method_signatures.get(UNBOUND, {})
        assert FuncName("add") in unbound_sigs
        sig = env.get_func_signature(FuncName("add"))
        assert sig.return_type == "Int"
        assert sig.params == (
            ("a", scalar(TypeName("Int"))),
            ("b", scalar(TypeName("Int"))),
        )

    def test_build_excludes_internal_func_labels(self):
        builder = TypeEnvironmentBuilder(
            func_return_types={
                "func_add_0": scalar(TypeName("Int")),
                "add": scalar(TypeName("Int")),
            },
            func_param_types={
                "func_add_0": [("a", scalar(TypeName("Int")))],
                "add": [("a", scalar(TypeName("Int")))],
            },
        )
        env = builder.build()
        unbound_sigs = env.method_signatures.get(UNBOUND, {})
        assert FuncName("add") in unbound_sigs
        assert FuncName("func_add_0") not in unbound_sigs

    def test_build_returns_frozen_mappings(self):
        builder = TypeEnvironmentBuilder(
            register_types={Register("%0"): scalar(TypeName("Int"))},
            var_types={"x": scalar(TypeName("Int"))},
        )
        env = builder.build()
        assert isinstance(env.register_types, MappingProxyType)
        assert isinstance(env.var_types, MappingProxyType)
        assert isinstance(env.method_signatures, MappingProxyType)

    def test_build_does_not_mutate_builder(self):
        builder = TypeEnvironmentBuilder(
            register_types={Register("%0"): scalar(TypeName("Int"))},
        )
        env = builder.build()
        builder.register_types[Register("%1")] = scalar(TypeName("Float"))
        assert Register("%1") not in env.register_types

    def test_func_signature_with_return_only(self):
        builder = TypeEnvironmentBuilder(
            func_return_types={"greet": scalar(TypeName("String"))}
        )
        env = builder.build()
        sig = env.get_func_signature(FuncName("greet"))
        assert sig.return_type == "String"
        assert sig.params == ()

    def test_func_signature_with_params_only(self):
        builder = TypeEnvironmentBuilder(
            func_param_types={
                "add": [("a", scalar(TypeName("Int"))), ("b", scalar(TypeName("Int")))]
            }
        )
        env = builder.build()
        sig = env.get_func_signature(FuncName("add"))
        assert sig.return_type == UNKNOWN
        assert sig.params == (
            ("a", scalar(TypeName("Int"))),
            ("b", scalar(TypeName("Int"))),
        )


class TestTypeEnvironmentStoresTypeExpr:
    """Verify that TypeEnvironment stores TypeExpr objects, not raw strings."""

    def test_register_types_are_type_expr(self):
        builder = TypeEnvironmentBuilder(
            register_types={Register("%0"): scalar(TypeName("Int"))}
        )
        env = builder.build()
        assert isinstance(env.register_types[Register("%0")], TypeExpr)
        assert isinstance(env.register_types[Register("%0")], ScalarType)

    def test_var_types_are_type_expr(self):
        builder = TypeEnvironmentBuilder(var_types={"x": scalar(TypeName("Float"))})
        env = builder.build()
        assert isinstance(env.var_types[VarName("x")], TypeExpr)
        assert isinstance(env.var_types[VarName("x")], ScalarType)

    def test_parameterized_type_preserved(self):
        builder = TypeEnvironmentBuilder(var_types={"ptr": parse_type("Pointer[Int]")})
        env = builder.build()
        assert isinstance(env.var_types[VarName("ptr")], ParameterizedType)
        assert env.var_types[VarName("ptr")].constructor == "Pointer"
        assert env.var_types[VarName("ptr")].arguments == (ScalarType(TypeName("Int")),)

    def test_func_signature_return_type_is_type_expr(self):
        builder = TypeEnvironmentBuilder(
            func_return_types={"add": scalar(TypeName("Int"))}
        )
        env = builder.build()
        assert isinstance(env.get_func_signature(FuncName("add")).return_type, TypeExpr)

    def test_func_signature_param_types_are_type_expr(self):
        builder = TypeEnvironmentBuilder(
            func_param_types={
                "f": [
                    ("x", scalar(TypeName("Int"))),
                    ("p", parse_type("Pointer[Float]")),
                ]
            }
        )
        env = builder.build()
        sig = env.get_func_signature(FuncName("f"))
        assert isinstance(sig.params[0][1], TypeExpr)
        assert isinstance(sig.params[1][1], ParameterizedType)
        assert sig.params[1][1] == "Pointer[Float]"

    def test_string_comparison_still_works(self):
        """Backward compat: env.register_types[Register("%0")] == 'Int' must hold."""
        builder = TypeEnvironmentBuilder(
            register_types={Register("%0"): scalar(TypeName("Int"))},
            var_types={"x": parse_type("Pointer[Int]")},
        )
        env = builder.build()
        assert env.register_types[Register("%0")] == "Int"
        assert env.var_types[VarName("x")] == "Pointer[Int]"
