"""Tests for class alias resolution in FunctionRegistry."""

from __future__ import annotations

from interpreter.registry import FunctionRegistry


class TestResolveClassName:
    """FunctionRegistry.resolve_class_name follows alias pointer chains."""

    def test_no_alias_returns_same_name(self):
        reg = FunctionRegistry()
        assert reg.resolve_class_name("Foo") == "Foo"

    def test_single_alias(self):
        reg = FunctionRegistry(class_aliases={"Foo": "__anon_class_0"})
        assert reg.resolve_class_name("Foo") == "__anon_class_0"

    def test_transitive_chain(self):
        reg = FunctionRegistry(
            class_aliases={"Baz": "Bar", "Bar": "Foo", "Foo": "__anon_class_0"}
        )
        assert reg.resolve_class_name("Baz") == "__anon_class_0"

    def test_cycle_terminates(self):
        reg = FunctionRegistry(class_aliases={"A": "B", "B": "A"})
        # Should not infinite loop; returns whichever it lands on
        result = reg.resolve_class_name("A")
        assert result in ("A", "B")

    def test_canonical_name_unchanged(self):
        reg = FunctionRegistry(
            classes={"__anon_class_0": "class___anon_class_0_0"},
            class_aliases={"Foo": "__anon_class_0"},
        )
        assert reg.resolve_class_name("__anon_class_0") == "__anon_class_0"

    def test_empty_string_unchanged(self):
        reg = FunctionRegistry()
        assert reg.resolve_class_name("") == ""
