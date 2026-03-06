"""Unit tests for TypeEnvironmentBuilder."""

from types import MappingProxyType

from interpreter.function_signature import FunctionSignature
from interpreter.type_environment_builder import TypeEnvironmentBuilder


class TestTypeEnvironmentBuilder:
    def test_build_empty_produces_empty_type_environment(self):
        builder = TypeEnvironmentBuilder()
        env = builder.build()
        assert dict(env.register_types) == {}
        assert dict(env.var_types) == {}
        assert dict(env.func_signatures) == {}

    def test_build_preserves_register_types(self):
        builder = TypeEnvironmentBuilder(register_types={"%0": "Int", "%1": "Float"})
        env = builder.build()
        assert env.register_types["%0"] == "Int"
        assert env.register_types["%1"] == "Float"

    def test_build_preserves_var_types(self):
        builder = TypeEnvironmentBuilder(var_types={"x": "Int", "name": "String"})
        env = builder.build()
        assert env.var_types["x"] == "Int"
        assert env.var_types["name"] == "String"

    def test_build_creates_func_signatures_from_return_and_param_types(self):
        builder = TypeEnvironmentBuilder(
            func_return_types={"add": "Int"},
            func_param_types={"add": [("a", "Int"), ("b", "Int")]},
        )
        env = builder.build()
        assert "add" in env.func_signatures
        sig = env.func_signatures["add"]
        assert sig.return_type == "Int"
        assert sig.params == (("a", "Int"), ("b", "Int"))

    def test_build_excludes_internal_func_labels(self):
        builder = TypeEnvironmentBuilder(
            func_return_types={"func_add_0": "Int", "add": "Int"},
            func_param_types={
                "func_add_0": [("a", "Int")],
                "add": [("a", "Int")],
            },
        )
        env = builder.build()
        assert "add" in env.func_signatures
        assert "func_add_0" not in env.func_signatures

    def test_build_returns_frozen_mappings(self):
        builder = TypeEnvironmentBuilder(
            register_types={"%0": "Int"},
            var_types={"x": "Int"},
        )
        env = builder.build()
        assert isinstance(env.register_types, MappingProxyType)
        assert isinstance(env.var_types, MappingProxyType)
        assert isinstance(env.func_signatures, MappingProxyType)

    def test_build_does_not_mutate_builder(self):
        builder = TypeEnvironmentBuilder(
            register_types={"%0": "Int"},
        )
        env = builder.build()
        builder.register_types["%1"] = "Float"
        assert "%1" not in env.register_types

    def test_func_signature_with_return_only(self):
        builder = TypeEnvironmentBuilder(func_return_types={"greet": "String"})
        env = builder.build()
        sig = env.func_signatures["greet"]
        assert sig.return_type == "String"
        assert sig.params == ()

    def test_func_signature_with_params_only(self):
        builder = TypeEnvironmentBuilder(
            func_param_types={"add": [("a", "Int"), ("b", "Int")]}
        )
        env = builder.build()
        sig = env.func_signatures["add"]
        assert sig.return_type == ""
        assert sig.params == (("a", "Int"), ("b", "Int"))
