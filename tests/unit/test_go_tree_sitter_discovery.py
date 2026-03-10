"""Discovery tests — kept for reference, all assertions positive."""

from __future__ import annotations

from interpreter.parser import TreeSitterParserFactory


def _parse(source: str):
    factory = TreeSitterParserFactory()
    parser = factory.get_parser("go")
    return parser.parse(source.encode("utf-8"))


def _collect_types(node, results=None):
    if results is None:
        results = []
    results.append(node.type)
    for c in node.children:
        _collect_types(c, results)
    return results


class TestGoTreeSitterDiscovery:
    def test_slice_type_conversion_is_type_conversion_expression(self):
        """[]byte(s) produces type_conversion_expression."""
        tree = _parse("package main; func main() { x := []byte(s) }")
        types = _collect_types(tree.root_node)
        assert "type_conversion_expression" in types

    def test_generic_type_conversion_is_type_conversion_expression(self):
        """Foo[int](y) produces type_conversion_expression."""
        tree = _parse("package main; func main() { x := Foo[int](y) }")
        types = _collect_types(tree.root_node)
        assert "type_conversion_expression" in types

    def test_int_conversion_is_call_expression(self):
        """int(y) is a call_expression, not type_conversion_expression."""
        tree = _parse("package main; func main() { x := int(y) }")
        types = _collect_types(tree.root_node)
        assert "call_expression" in types
        assert "type_conversion_expression" not in types

    def test_generic_composite_literal_has_generic_type(self):
        """Foo[int]{} composite literal has generic_type child."""
        tree = _parse("package main; func main() { x := Foo[int]{} }")
        types = _collect_types(tree.root_node)
        assert "generic_type" in types
        assert "composite_literal" in types
