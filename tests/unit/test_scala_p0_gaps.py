"""Tests for Scala P0 gaps: generic_function, postfix_expression, stable_type_identifier."""

from __future__ import annotations

from interpreter.frontends.scala import ScalaFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_scala(source: str) -> list[IRInstruction]:
    frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
    return frontend.lower(source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


# -- generic_function ----------------------------------------------------------


class TestScalaGenericFunction:
    """generic_function: foo[Int](x), list.asInstanceOf[Bar], List.empty[Int]."""

    def test_generic_function_call_no_symbolic(self):
        """foo[Int](x) should NOT produce unsupported:generic_function."""
        instructions = _parse_scala("object M { val r = foo[Int](x) }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:generic_function" in str(inst.operands) for inst in symbolics
        )

    def test_generic_function_call_produces_call(self):
        """foo[Int](x) should lower as CALL_FUNCTION to 'foo'."""
        instructions = _parse_scala("object M { val r = foo[Int](x) }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("foo" in inst.operands for inst in calls)

    def test_generic_method_call_no_symbolic(self):
        """list.asInstanceOf[Bar] should NOT produce unsupported:generic_function."""
        instructions = _parse_scala("object M { val r = list.asInstanceOf[Bar] }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:generic_function" in str(inst.operands) for inst in symbolics
        )

    def test_generic_method_call_produces_load_field(self):
        """list.asInstanceOf[Bar] (no call parens) should produce LOAD_FIELD for asInstanceOf."""
        instructions = _parse_scala("object M { val r = list.asInstanceOf[Bar] }")
        fields = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("asInstanceOf" in inst.operands for inst in fields)

    def test_generic_method_with_args_produces_call_method(self):
        """list.map[Int](f) should produce CALL_METHOD."""
        instructions = _parse_scala("object M { val r = list.map[Int](f) }")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("map" in inst.operands for inst in calls)

    def test_generic_static_call_no_symbolic(self):
        """List.empty[Int] should NOT produce unsupported:generic_function."""
        instructions = _parse_scala("object M { val r = List.empty[Int] }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:generic_function" in str(inst.operands) for inst in symbolics
        )

    def test_generic_static_call_produces_load_field(self):
        """List.empty[Int] (no call parens) should produce LOAD_FIELD for 'empty'."""
        instructions = _parse_scala("object M { val r = List.empty[Int] }")
        fields = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("empty" in inst.operands for inst in fields)

    def test_generic_function_result_stored(self):
        """Result of foo[Int](x) should be stored in 'r'."""
        instructions = _parse_scala("object M { val r = foo[Int](x) }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("r" in inst.operands for inst in stores)


# -- postfix_expression --------------------------------------------------------


class TestScalaPostfixExpression:
    """postfix_expression: list sorted, future await."""

    def test_postfix_no_symbolic(self):
        """'list sorted' should NOT produce unsupported:postfix_expression."""
        instructions = _parse_scala("object M { val r = list sorted }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:postfix_expression" in str(inst.operands) for inst in symbolics
        )

    def test_postfix_produces_call_method(self):
        """'list sorted' should lower as CALL_METHOD('sorted') on 'list' with 0 args."""
        instructions = _parse_scala("object M { val r = list sorted }")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("sorted" in inst.operands for inst in calls)

    def test_postfix_loads_receiver(self):
        """The receiver 'list' should be loaded."""
        instructions = _parse_scala("object M { val r = list sorted }")
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("list" in inst.operands for inst in loads)

    def test_postfix_result_stored(self):
        """Result of 'list sorted' should be stored in 'r'."""
        instructions = _parse_scala("object M { val r = list sorted }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("r" in inst.operands for inst in stores)

    def test_postfix_call_method_has_zero_extra_args(self):
        """CALL_METHOD for 'list sorted' should have [receiver_reg, 'sorted'] only."""
        instructions = _parse_scala("object M { val r = list sorted }")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        method_calls = [c for c in calls if "sorted" in c.operands]
        assert len(method_calls) == 1
        # operands: [obj_reg, method_name] -- length 2 means 0 extra args
        assert len(method_calls[0].operands) == 2


# -- stable_type_identifier ---------------------------------------------------


class TestScalaStableTypeIdentifier:
    """stable_type_identifier: pkg.MyClass in type positions."""

    def test_stable_type_id_in_typed_pattern_no_symbolic(self):
        """'case _: pkg.MyClass => ...' should NOT produce unsupported:stable_type_identifier."""
        instructions = _parse_scala(
            "object M { val r = x match { case _: pkg.MyClass => 1 } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:stable_type_identifier" in str(inst.operands)
            for inst in symbolics
        )

    def test_stable_type_id_in_case_class_pattern_no_symbolic(self):
        """'case pkg.Foo(x) => x' should NOT produce unsupported:stable_type_identifier."""
        instructions = _parse_scala(
            "object M { val r = x match { case pkg.Foo(y) => y } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:stable_type_identifier" in str(inst.operands)
            for inst in symbolics
        )

    def test_stable_type_id_in_case_class_pattern_produces_new_object(self):
        """'case pkg.Foo(y) => y' should produce NEW_OBJECT with 'pattern:pkg.Foo'."""
        instructions = _parse_scala(
            "object M { val r = x match { case pkg.Foo(y) => y } }"
        )
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("pkg.Foo" in str(inst.operands) for inst in new_objs)

    def test_stable_type_id_lowered_directly_produces_load_chain(self):
        """When stable_type_identifier appears in expression context, it produces
        LOAD_VAR + LOAD_FIELD chain."""
        instructions = _parse_scala("object M { val r: pkg.MyClass = null }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("r" in inst.operands for inst in stores)

    def test_stable_type_id_as_val_type_annotation(self):
        """'val r: pkg.MyClass = null' -- type annotation should not crash."""
        frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
        instructions = frontend.lower(b"object M { val r: pkg.MyClass = null }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("r" in inst.operands for inst in stores)
