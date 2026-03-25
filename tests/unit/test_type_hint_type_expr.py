"""Tests for TypeExpr-valued type_hint on NewObject and NewArray."""

from interpreter.instructions import NewObject, NewArray
from interpreter.ir import IRInstruction, Opcode
from interpreter.register import Register
from interpreter.types.type_expr import UNKNOWN, ScalarType, TypeExpr, scalar


class TestNewObjectTypeHintScalarPrep:
    """Verify scalar() values work with the current str field via __str__."""

    def test_scalar_str_matches_plain_string(self):
        assert str(scalar("dict")) == "dict"

    def test_scalar_in_new_object_operands(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=scalar("Foo"))
        assert inst.operands == ["Foo"]

    def test_scalar_in_new_array_operands(self):
        inst = NewArray(
            result_reg=Register("%r1"),
            type_hint=scalar("list"),
            size_reg=Register("%r0"),
        )
        assert inst.operands == ["list", "%r0"]
