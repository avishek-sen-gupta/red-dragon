# pyright: standard
"""Unit tests for TypeScriptTypeAliasExtractor."""

from tests.covers import covers
from interpreter.frontends.typescript.features import TypeScriptFeature
from interpreter.frontends.typescript.type_alias_extractor import (
    TypeScriptTypeAliasExtractor,
)
from interpreter.type_name import TypeName
from interpreter.types.type_expr import ScalarType


class _FakeTSNode:
    """Fake tree-sitter node supporting child_by_field_name."""

    def __init__(
        self,
        kind: str,
        *,
        fields: dict[str, "_FakeTSNode"] | None = None,
        text: bytes = b"",
    ):
        self.type = kind
        self._fields = fields or {}
        self.text = text

    def child_by_field_name(self, name: str) -> "_FakeTSNode | None":
        return self._fields.get(name)


def _type_alias_decl(
    alias_name: str, underlying_type: str, value_node_kind: str = "predefined_type"
) -> _FakeTSNode:
    return _FakeTSNode(
        "type_alias_declaration",
        fields={
            "name": _FakeTSNode("type_identifier", text=alias_name.encode()),
            "value": _FakeTSNode(value_node_kind, text=underlying_type.encode()),
        },
    )


class TestTypeScriptTypeAliasExtractorMatches:
    @covers(TypeScriptFeature.TYPE_ALIAS)
    def test_matches_predefined_type_alias(self) -> None:
        extractor = TypeScriptTypeAliasExtractor()
        node = _type_alias_decl("UserId", "number")
        assert extractor.matches(node)

    @covers(TypeScriptFeature.TYPE_ALIAS)
    def test_matches_type_identifier_alias(self) -> None:
        extractor = TypeScriptTypeAliasExtractor()
        node = _type_alias_decl(
            "MyAlias", "SomeClass", value_node_kind="type_identifier"
        )
        assert extractor.matches(node)

    @covers(TypeScriptFeature.TYPE_ALIAS)
    def test_does_not_match_non_alias_node(self) -> None:
        extractor = TypeScriptTypeAliasExtractor()
        node = _FakeTSNode("variable_declaration")
        assert not extractor.matches(node)

    @covers(TypeScriptFeature.TYPE_ALIAS)
    def test_does_not_match_generic_alias(self) -> None:
        extractor = TypeScriptTypeAliasExtractor()
        node = _type_alias_decl("Complex", "Array<T>", value_node_kind="generic_type")
        assert not extractor.matches(node)


class TestTypeScriptTypeAliasExtractorExtract:
    @covers(TypeScriptFeature.TYPE_ALIAS)
    def test_extract_maps_predefined_number(self) -> None:
        extractor = TypeScriptTypeAliasExtractor()
        node = _type_alias_decl("UserId", "number")
        type_map = {"number": "Float", "string": "String"}
        name, expr = extractor.extract(node, type_map)
        assert name == TypeName("UserId")
        assert expr == ScalarType(TypeName("Float"))

    @covers(TypeScriptFeature.TYPE_ALIAS)
    def test_extract_maps_predefined_string(self) -> None:
        extractor = TypeScriptTypeAliasExtractor()
        node = _type_alias_decl("Label", "string")
        type_map = {"number": "Float", "string": "String"}
        name, expr = extractor.extract(node, type_map)
        assert name == TypeName("Label")
        assert expr == ScalarType(TypeName("String"))
