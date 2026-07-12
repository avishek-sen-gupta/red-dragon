# pyright: standard
"""Unit tests for GoTypeAliasExtractor."""

from interpreter.frontends.go.features import GoFeature
from interpreter.frontends.go.type_alias_extractor import GoTypeAliasExtractor
from interpreter.type_name import TypeName
from interpreter.types.type_expr import ScalarType
from tests.covers import covers


class _FakeGoNode:
    """Fake tree-sitter node supporting child_by_field_name."""

    def __init__(
        self,
        kind: str,
        *,
        fields: dict[str, "_FakeGoNode"] | None = None,
        text: bytes = b"",
    ):
        self.type = kind
        self._fields = fields or {}
        self.text = text
        self.children: list[_FakeGoNode] = list(fields.values()) if fields else []

    def child_by_field_name(self, name: str) -> "_FakeGoNode | None":
        return self._fields.get(name)


def _type_spec(
    alias_name: str, underlying_type: str, type_node_kind: str = "type_identifier"
) -> _FakeGoNode:
    return _FakeGoNode(
        "type_spec",
        fields={
            "name": _FakeGoNode("type_identifier", text=alias_name.encode()),
            "type": _FakeGoNode(type_node_kind, text=underlying_type.encode()),
        },
    )


class TestGoTypeAliasExtractorMatches:
    @covers(GoFeature.TYPE_ALIAS)
    def test_matches_type_spec_with_type_identifier(self) -> None:
        extractor = GoTypeAliasExtractor()
        node = _type_spec("UserId", "int")
        assert extractor.matches(node)

    @covers(GoFeature.TYPE_ALIAS)
    def test_does_not_match_non_type_spec(self) -> None:
        extractor = GoTypeAliasExtractor()
        node = _FakeGoNode("var_declaration")
        assert not extractor.matches(node)

    @covers(GoFeature.TYPE_ALIAS)
    def test_does_not_match_struct_type_spec(self) -> None:
        extractor = GoTypeAliasExtractor()
        node = _type_spec("Point", "struct_body", type_node_kind="struct_type")
        assert not extractor.matches(node)

    @covers(GoFeature.TYPE_ALIAS)
    def test_does_not_match_interface_type_spec(self) -> None:
        extractor = GoTypeAliasExtractor()
        node = _type_spec("Stringer", "interface_body", type_node_kind="interface_type")
        assert not extractor.matches(node)


class TestGoTypeAliasExtractorExtract:
    @covers(GoFeature.TYPE_ALIAS)
    def test_extract_maps_known_type(self) -> None:
        extractor = GoTypeAliasExtractor()
        node = _type_spec("UserId", "int")
        type_map = {"int": "Int", "string": "String"}
        name, expr = extractor.extract(node, type_map)
        assert name == TypeName("UserId")
        assert expr == ScalarType(TypeName("Int"))

    @covers(GoFeature.TYPE_ALIAS)
    def test_extract_passes_through_unknown_type(self) -> None:
        extractor = GoTypeAliasExtractor()
        node = _type_spec("MyFloat", "float64")
        type_map = {"float64": "Float"}
        name, expr = extractor.extract(node, type_map)
        assert name == TypeName("MyFloat")
        assert expr == ScalarType(TypeName("Float"))
