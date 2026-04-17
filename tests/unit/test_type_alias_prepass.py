# pyright: standard
"""Tests for the type alias prepass infrastructure."""

from typing import Any

from tests.covers import covers
from interpreter.frontends.type_alias_prepass import (
    NullTypeAliasExtractor,
    collect_type_aliases,
)
from interpreter.type_name import TypeName
from interpreter.types.type_expr import ScalarType, TypeExpr

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeNode:
    """Minimal fake tree-sitter node."""

    def __init__(self, kind: str, *, children: list["_FakeNode"] | None = None):
        self.type = kind
        self.children: list[_FakeNode] = children or []


class _SimpleExtractor:
    """Extractor that matches nodes of type 'alias_decl'."""

    def __init__(self, alias_name: TypeName, target: TypeExpr):
        self._alias_name = alias_name
        self._target = target

    def matches(self, node: Any) -> bool:
        return getattr(node, "type", None) == "alias_decl"

    def extract(self, node: Any, type_map: dict[str, str]) -> tuple[TypeName, TypeExpr]:
        return self._alias_name, self._target


class TestNullTypeAliasExtractor:
    @covers("type_alias_prepass.NullTypeAliasExtractor.matches")
    def test_null_extractor_never_matches(self) -> None:
        extractor = NullTypeAliasExtractor()
        assert not extractor.matches(object())


class TestCollectTypeAliases:
    @covers("type_alias_prepass.collect_type_aliases.null_extractor")
    def test_null_extractor_yields_empty_dict(self) -> None:
        """A NullTypeAliasExtractor produces no aliases regardless of AST shape."""
        root = _FakeNode("root", children=[_FakeNode("alias_decl")])
        result = collect_type_aliases(root, NullTypeAliasExtractor(), {})
        assert result == {}

    @covers("type_alias_prepass.collect_type_aliases.real_extractor")
    def test_matching_node_at_root_is_collected(self) -> None:
        root = _FakeNode("alias_decl")
        extractor = _SimpleExtractor(TypeName("UserId"), ScalarType(TypeName("Int")))
        result = collect_type_aliases(root, extractor, {})
        assert result == {TypeName("UserId"): ScalarType(TypeName("Int"))}

    @covers("type_alias_prepass.collect_type_aliases.children")
    def test_matching_node_in_children_is_collected(self) -> None:
        root = _FakeNode("root", children=[_FakeNode("alias_decl")])
        extractor = _SimpleExtractor(TypeName("Name"), ScalarType(TypeName("String")))
        result = collect_type_aliases(root, extractor, {})
        assert result == {TypeName("Name"): ScalarType(TypeName("String"))}


class TestBaseFrontendIntegration:
    """BaseFrontend exposes _type_alias_extractor field (NullTypeAliasExtractor by default)."""

    @covers("type_alias_prepass.base_frontend.default_extractor")
    def test_base_frontend_has_null_extractor_by_default(self) -> None:
        from unittest.mock import MagicMock
        from interpreter.frontends._base import BaseFrontend
        from interpreter.frontends.type_alias_prepass import NullTypeAliasExtractor

        frontend = BaseFrontend.__new__(BaseFrontend)
        frontend.__init__(MagicMock(), MagicMock())  # type: ignore[call-arg]
        assert isinstance(frontend._type_alias_extractor, NullTypeAliasExtractor)


class TestTypeAliasDataModel:
    """type_aliases dict uses TypeName keys throughout the data model."""

    @covers("type_alias_prepass.data_model.builder_key_type")
    def test_builder_accepts_typename_keys(self) -> None:
        from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
        from interpreter.types.type_expr import scalar

        builder = TypeEnvironmentBuilder()
        key = TypeName("UserId")
        builder.type_aliases[key] = scalar(TypeName("Int"))
        assert builder.type_aliases[key] == "Int"

    @covers("type_alias_prepass.data_model.environment_key_type")
    def test_built_environment_has_typename_keys(self) -> None:
        from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
        from interpreter.types.type_expr import scalar

        builder = TypeEnvironmentBuilder()
        key = TypeName("Score")
        builder.type_aliases[key] = scalar(TypeName("Float"))
        env = builder.build()
        assert env.type_aliases[key] == "Float"
