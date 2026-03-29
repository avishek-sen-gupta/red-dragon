"""Tests for TypeExpr-valued type_hint on NewObject and NewArray."""

from interpreter.instructions import (
    CallCtorFunction,
    NewObject,
    NewArray,
    InstructionBase,
)
from interpreter.ir import IRInstruction, Opcode
from interpreter.register import Register
from interpreter.types.type_expr import (
    UNKNOWN,
    AnnotationType,
    EnumType,
    ParameterizedType,
    ScalarType,
    StructPatternType,
    TypeExpr,
    scalar,
)


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
            opcode=Opcode.NEW_OBJECT, result_reg=Register("%r0"), operands=["Foo"]
        )
        assert isinstance(inst.type_hint, ScalarType)
        assert inst.type_hint == scalar("Foo")

    def test_factory_empty_operands_gives_unknown(self):
        inst = IRInstruction(
            opcode=Opcode.NEW_OBJECT, result_reg=Register("%r0"), operands=[]
        )
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
            result_reg=Register("%r1"),
            operands=["list", "%r0"],
        )
        assert isinstance(inst.type_hint, ScalarType)
        assert inst.type_hint == scalar("list")


class TestEnumType:
    def test_is_type_expr(self):
        t = EnumType("Color")
        assert isinstance(t, TypeExpr)

    def test_str_representation(self):
        assert str(EnumType("Color")) == "enum:Color"

    def test_equality(self):
        assert EnumType("Color") == EnumType("Color")
        assert EnumType("Color") != EnumType("Shape")
        assert EnumType("Color") != scalar("Color")

    def test_in_new_object(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=EnumType("Color"))
        assert inst.operands == ["enum:Color"]
        assert str(inst) == "%r0 = new_object enum:Color"

    def test_hash(self):
        assert hash(EnumType("Color")) == hash(EnumType("Color"))
        s = {EnumType("Color"), EnumType("Shape")}
        assert len(s) == 2


class TestAnnotationType:
    def test_is_type_expr(self):
        assert isinstance(AnnotationType("Override"), TypeExpr)

    def test_str_representation(self):
        assert str(AnnotationType("Override")) == "annotation:Override"

    def test_in_new_object(self):
        inst = NewObject(
            result_reg=Register("%r0"), type_hint=AnnotationType("Override")
        )
        assert inst.operands == ["annotation:Override"]


class TestStructPatternType:
    def test_is_type_expr(self):
        assert isinstance(StructPatternType("Point"), TypeExpr)

    def test_str_representation(self):
        assert str(StructPatternType("Point")) == "struct_pattern:Point"

    def test_in_new_object(self):
        inst = NewObject(
            result_reg=Register("%r0"), type_hint=StructPatternType("Point")
        )
        assert inst.operands == ["struct_pattern:Point"]


class TestCallCtorFunction:
    def test_is_instruction(self):
        inst = CallCtorFunction(
            result_reg=Register("%r0"),
            func_name="ArrayList",
            type_hint=ParameterizedType("ArrayList", (scalar("Integer"),)),
            args=(Register("%r1"),),
        )
        assert isinstance(inst, InstructionBase)
        assert inst.opcode == Opcode.CALL_CTOR
        assert inst.func_name == "ArrayList"
        assert inst.type_hint == ParameterizedType("ArrayList", (scalar("Integer"),))
        assert inst.args == (Register("%r1"),)

    def test_non_generic_constructor(self):
        inst = CallCtorFunction(
            result_reg=Register("%r0"),
            func_name="Foo",
            type_hint=scalar("Foo"),
            args=(),
        )
        assert inst.type_hint == scalar("Foo")
        assert str(inst) == "%r0 = call_ctor Foo"

    def test_with_args_str(self):
        inst = CallCtorFunction(
            result_reg=Register("%r0"),
            func_name="Point",
            type_hint=scalar("Point"),
            args=(Register("%r1"), Register("%r2")),
        )
        assert str(inst) == "%r0 = call_ctor Point %r1 %r2"

    def test_parameterized_type_in_operands(self):
        inst = CallCtorFunction(
            result_reg=Register("%r0"),
            func_name="HashMap",
            type_hint=ParameterizedType("HashMap", (scalar("String"), scalar("Int"))),
            args=(),
        )
        # operands should render func_name as string for __str__ compat
        assert inst.operands[0] == "HashMap"

    def test_in_new_object(self):
        inst = NewObject(
            result_reg=Register("%r0"), type_hint=StructPatternType("Point")
        )
        assert inst.operands == ["struct_pattern:Point"]
