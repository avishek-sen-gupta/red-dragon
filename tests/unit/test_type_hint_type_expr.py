"""Tests for TypeExpr-valued type_hint on NewObject and NewArray."""

from interpreter.instructions import NewObject, NewArray
from interpreter.ir import IRInstruction, Opcode
from interpreter.register import Register
from interpreter.types.type_expr import UNKNOWN, ScalarType, TypeExpr, scalar


class TestNewObjectTypeHint:
    def test_type_hint_is_type_expr(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=scalar("Foo"))
        assert isinstance(inst.type_hint, TypeExpr)
        assert isinstance(inst.type_hint, ScalarType)
        assert inst.type_hint == scalar("Foo")

    def test_default_is_unknown(self):
        inst = NewObject(result_reg=Register("%r0"))
        assert inst.type_hint is UNKNOWN
        assert not inst.type_hint

    def test_operands_renders_as_string(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=scalar("dict"))
        assert inst.operands == ["dict"]
        assert isinstance(inst.operands[0], str)

    def test_operands_empty_when_unknown(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=UNKNOWN)
        assert inst.operands == []

    def test_str_matches_flat_format(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=scalar("Foo"))
        assert str(inst) == "%r0 = new_object Foo"

    def test_factory_wraps_string_as_scalar(self):
        inst = IRInstruction(
            opcode=Opcode.NEW_OBJECT, result_reg="%r0", operands=["Foo"]
        )
        assert isinstance(inst.type_hint, ScalarType)
        assert inst.type_hint == scalar("Foo")

    def test_factory_empty_operands_gives_unknown(self):
        inst = IRInstruction(opcode=Opcode.NEW_OBJECT, result_reg="%r0", operands=[])
        assert inst.type_hint is UNKNOWN


class TestNewArrayTypeHint:
    def test_type_hint_is_type_expr(self):
        inst = NewArray(
            result_reg=Register("%r1"),
            type_hint=scalar("list"),
            size_reg=Register("%r0"),
        )
        assert isinstance(inst.type_hint, TypeExpr)
        assert inst.type_hint == scalar("list")

    def test_default_is_unknown(self):
        inst = NewArray(result_reg=Register("%r1"), size_reg=Register("%r0"))
        assert inst.type_hint is UNKNOWN

    def test_operands_renders_as_string(self):
        inst = NewArray(
            result_reg=Register("%r1"),
            type_hint=scalar("tuple"),
            size_reg=Register("%r0"),
        )
        assert inst.operands == ["tuple", "%r0"]
        assert isinstance(inst.operands[0], str)

    def test_str_matches_flat_format(self):
        inst = NewArray(
            result_reg=Register("%r1"),
            type_hint=scalar("list"),
            size_reg=Register("%r0"),
        )
        assert str(inst) == "%r1 = new_array list %r0"

    def test_factory_wraps_string_as_scalar(self):
        inst = IRInstruction(
            opcode=Opcode.NEW_ARRAY,
            result_reg="%r1",
            operands=["list", "%r0"],
        )
        assert isinstance(inst.type_hint, ScalarType)
        assert inst.type_hint == scalar("list")
