"""Tests for TypeNode — type hierarchy DAG node."""

import pytest

from interpreter.types.type_node import TypeNode


class TestTypeNode:
    def test_frozen_immutable(self):
        node = TypeNode(name="Int", parents=("Number",))
        with pytest.raises(AttributeError):
            node.name = "Float"

    def test_parents_tuple(self):
        node = TypeNode(name="Int", parents=("Number",))
        assert node.parents == ("Number",)

    def test_default_parents_empty(self):
        node = TypeNode(name="Any")
        assert node.parents == ()

    def test_multiple_parents(self):
        node = TypeNode(name="Printable", parents=("String", "Object"))
        assert node.parents == ("String", "Object")
