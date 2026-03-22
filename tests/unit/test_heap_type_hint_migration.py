"""Tests for HeapObject.type_hint migration from str to TypeExpr."""

from interpreter.types.type_expr import (
    ScalarType,
    ParameterizedType,
    UNKNOWN,
    scalar,
    parse_type,
)
from interpreter.vm_types import HeapObject


class TestHeapObjectTypeHint:
    def test_default_type_hint_is_unknown(self):
        obj = HeapObject()
        assert obj.type_hint == UNKNOWN
        assert not obj.type_hint  # UNKNOWN is falsy

    def test_scalar_type_hint(self):
        obj = HeapObject(type_hint=scalar("Node"))
        assert obj.type_hint == "Node"  # string compatibility
        assert isinstance(obj.type_hint, ScalarType)

    def test_parameterized_type_hint(self):
        box_node = ParameterizedType("Box", (ScalarType("Node"),))
        obj = HeapObject(type_hint=box_node)
        assert obj.type_hint == "Box[Node]"  # string compatibility
        assert isinstance(obj.type_hint, ParameterizedType)
        assert obj.type_hint.constructor == "Box"
        assert obj.type_hint.arguments == (ScalarType("Node"),)

    def test_nested_parameterized_type_hint(self):
        opt_box_node = ParameterizedType(
            "Option",
            (ParameterizedType("Box", (ScalarType("Node"),)),),
        )
        obj = HeapObject(type_hint=opt_box_node)
        assert obj.type_hint == "Option[Box[Node]]"

    def test_to_dict_with_type_expr(self):
        obj = HeapObject(type_hint=scalar("Node"))
        d = obj.to_dict()
        assert d["type_hint"] == "Node"

    def test_to_dict_with_unknown(self):
        obj = HeapObject()
        d = obj.to_dict()
        assert d["type_hint"] is None  # preserve JSON shape

    def test_to_dict_with_parameterized(self):
        obj = HeapObject(type_hint=ParameterizedType("Box", (ScalarType("Node"),)))
        d = obj.to_dict()
        assert d["type_hint"] == "Box[Node]"
