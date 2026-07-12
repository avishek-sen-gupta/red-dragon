# pyright: standard
"""Unit tests for RustTypeAliasExtractor."""

from interpreter.frontends.rust.features import RustFeature
from interpreter.frontends.rust.type_alias_extractor import RustTypeAliasExtractor
from interpreter.type_name import TypeName
from interpreter.types.type_expr import ScalarType
from tests.covers import covers


class _FakeRustNode:
    """Fake tree-sitter node supporting child_by_field_name."""

    def __init__(
        self,
        kind: str,
        *,
        fields: dict[str, "_FakeRustNode"] | None = None,
        text: bytes = b"",
    ):
        self.type = kind
        self._fields = fields or {}
        self.text = text

    def child_by_field_name(self, name: str) -> "_FakeRustNode | None":
        return self._fields.get(name)


def _type_item(
    alias_name: str, underlying_type: str, type_node_kind: str = "primitive_type"
) -> _FakeRustNode:
    return _FakeRustNode(
        "type_item",
        fields={
            "name": _FakeRustNode("type_identifier", text=alias_name.encode()),
            "type": _FakeRustNode(type_node_kind, text=underlying_type.encode()),
        },
    )


class TestRustTypeAliasExtractorMatches:
    @covers(RustFeature.TYPE_ITEM)
    def test_matches_type_item_with_type_identifier(self) -> None:
        extractor = RustTypeAliasExtractor()
        node = _type_item("UserId", "i32")
        assert extractor.matches(node)

    @covers(RustFeature.TYPE_ITEM)
    def test_does_not_match_non_type_item(self) -> None:
        extractor = RustTypeAliasExtractor()
        node = _FakeRustNode("let_declaration")
        assert not extractor.matches(node)

    @covers(RustFeature.TYPE_ITEM)
    def test_does_not_match_generic_type_item(self) -> None:
        extractor = RustTypeAliasExtractor()
        node = _type_item("VecAlias", "Vec<i32>", type_node_kind="generic_type")
        assert not extractor.matches(node)

    def test_matches_type_item_with_type_identifier(self) -> None:
        """type MyAlias = SomeStruct; — type field is type_identifier."""
        extractor = RustTypeAliasExtractor()
        node = _type_item("MyAlias", "SomeStruct", type_node_kind="type_identifier")
        assert extractor.matches(node)


class TestRustTypeAliasExtractorExtract:
    @covers(RustFeature.TYPE_ITEM)
    def test_extract_maps_known_type(self) -> None:
        extractor = RustTypeAliasExtractor()
        node = _type_item("UserId", "i32")
        type_map = {"i32": "Int", "f64": "Float"}
        name, expr = extractor.extract(node, type_map)
        assert name == TypeName("UserId")
        assert expr == ScalarType(TypeName("Int"))

    @covers(RustFeature.TYPE_ITEM)
    def test_extract_passes_through_unknown_type(self) -> None:
        extractor = RustTypeAliasExtractor()
        node = _type_item("Score", "f64")
        type_map = {"f64": "Float"}
        name, expr = extractor.extract(node, type_map)
        assert name == TypeName("Score")
        assert expr == ScalarType(TypeName("Float"))
