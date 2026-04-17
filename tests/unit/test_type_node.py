"""Tests for TypeNode — type hierarchy DAG node."""

import pytest

from interpreter.type_name import TypeName
from interpreter.types.type_node import TypeNode


class TestTypeNode:
    def test_frozen_immutable(self):
        node = TypeNode(name=TypeName("Int"), parents=(TypeName("Number"),))
        with pytest.raises(AttributeError):
            node.name = TypeName("Float")

    def test_parents_tuple(self):
        node = TypeNode(name=TypeName("Int"), parents=(TypeName("Number"),))
        assert node.parents == (TypeName("Number"),)

    def test_default_parents_empty(self):
        node = TypeNode(name=TypeName("Any"))
        assert node.parents == ()

    def test_multiple_parents(self):
        node = TypeNode(
            name=TypeName("Printable"), parents=(TypeName("String"), TypeName("Object"))
        )
        assert node.parents == (TypeName("String"), TypeName("Object"))
