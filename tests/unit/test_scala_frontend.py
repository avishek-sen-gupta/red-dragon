"""Tests for ScalaFrontend -- tree-sitter Scala AST to IR lowering."""

from __future__ import annotations

import pytest

from interpreter.frontends.scala import ScalaFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment_builder import TypeEnvironmentBuilder


def _parse_scala(source: str) -> list[IRInstruction]:
    frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
    return frontend.lower(source.encode("utf-8"))


def _parse_scala_with_types(
    source: str,
) -> tuple[list[IRInstruction], TypeEnvironmentBuilder]:
    frontend = ScalaFrontend(TreeSitterParserFactory(), "scala")
    instructions = frontend.lower(source.encode("utf-8"))
    return instructions, frontend.type_env_builder


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestScalaDeclarations:
    def test_val_definition(self):
        instructions = _parse_scala("object M { val x = 10 }")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_var_definition(self):
        instructions = _parse_scala("object M { var y = 5 }")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)

    def test_var_assignment(self):
        instructions = _parse_scala("object M { var y = 5; y = 10 }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("10" in inst.operands for inst in consts)


class TestScalaFunctions:
    def test_function_definition(self):
        instructions = _parse_scala("object M { def add(a: Int, b: Int): Int = a + b }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        assert Opcode.RETURN in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("add" in inst.operands for inst in stores)

    def test_function_call(self):
        instructions = _parse_scala("object M { val r = add(1, 2) }")
        # The call should produce either CALL_FUNCTION or CALL_UNKNOWN
        all_calls = _find_all(instructions, Opcode.CALL_FUNCTION) + _find_all(
            instructions, Opcode.CALL_UNKNOWN
        )
        assert len(all_calls) >= 1

    def test_return_via_expression(self):
        instructions = _parse_scala("object M { def answer(): Int = { 42 } }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        # The function body should contain the constant 42
        consts = _find_all(instructions, Opcode.CONST)
        const_values = [str(v) for inst in consts for v in inst.operands]
        assert any("42" in v for v in const_values)


class TestScalaControlFlow:
    def test_if_expression_value_producing(self):
        instructions = _parse_scala("object M { val y = if (x > 0) 1 else 0 }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("if_true" in (inst.label or "") for inst in labels)

    def test_while_loop(self):
        instructions = _parse_scala(
            "object M { var x = 10; while (x > 0) { x = x - 1 } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_match_expression(self):
        instructions = _parse_scala(
            "object M { val r = x match { case 1 => 10; case _ => 0 } }"
        )
        opcodes = _opcodes(instructions)
        assert (
            Opcode.BRANCH_IF in opcodes
        ), "match expression must produce BRANCH_IF for case dispatch"
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("case" in (inst.label or "") for inst in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)

    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/else-if/else-if/else must produce IR."""
        instructions = _parse_scala(
            "object M { if (x==1) { y=10 }"
            " else if (x==2) { y=20 }"
            " else if (x==3) { y=30 }"
            " else { y=40 } }"
        )
        consts = _find_all(instructions, Opcode.CONST)
        const_values = [op for inst in consts for op in inst.operands]
        assert "10" in const_values, "if-branch value missing"
        assert "20" in const_values, "first else-if-branch value missing"
        assert "30" in const_values, "second else-if-branch value missing"
        assert "40" in const_values, "else-branch value missing"

        branch_ifs = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) == 3

        labels = _labels_in_order(instructions)
        branch_targets = {
            target for inst in branch_ifs for target in inst.label.split(",")
        }
        label_set = set(labels)
        assert branch_targets.issubset(
            label_set
        ), f"Unreachable targets: {branch_targets - label_set}"


class TestScalaClasses:
    def test_class_definition(self):
        instructions = _parse_scala('class Dog { def bark(): String = "woof" }')
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_object_definition_singleton(self):
        instructions = _parse_scala("object Singleton { val x = 42 }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Singleton" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)


class TestScalaExpressions:
    def test_infix_expression_binary_op(self):
        instructions = _parse_scala("object M { val z = a + b }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_block_as_expression(self):
        instructions = _parse_scala("object M { val v = { val a = 1; a + 2 } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("v" in inst.operands for inst in stores)

    def test_field_access(self):
        instructions = _parse_scala("object M { val f = obj.field }")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_FIELD in opcodes
        fields = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("field" in inst.operands for inst in fields)

    def test_string_literal(self):
        instructions = _parse_scala('object M { val s = "hello" }')
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"hello"' in inst.operands for inst in consts)

    def test_boolean_literal(self):
        instructions = _parse_scala("object M { val b = true }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("True" in inst.operands for inst in consts)


class TestScalaSpecial:
    def test_empty_program(self):
        instructions = _parse_scala("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_fallback_symbolic(self):
        """Unhandled node types (ascription_expression) should produce SYMBOLIC unsupported."""
        instructions = _parse_scala("object M { val x = (y: Int) }")
        opcodes = _opcodes(instructions)
        assert Opcode.SYMBOLIC in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_return_last_expression_in_block(self):
        instructions = _parse_scala(
            "object M { def compute(): Int = { val a = 1; val b = 2; a + b } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        assert Opcode.RETURN in opcodes

    def test_method_call(self):
        instructions = _parse_scala("object M { val r = obj.doSomething(1) }")
        # Should produce CALL_METHOD or at least some call-related opcode
        all_calls = (
            _find_all(instructions, Opcode.CALL_METHOD)
            + _find_all(instructions, Opcode.CALL_FUNCTION)
            + _find_all(instructions, Opcode.CALL_UNKNOWN)
        )
        assert len(all_calls) >= 1

    def test_null_literal(self):
        instructions = _parse_scala("object M { val n = null }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("None" in inst.operands for inst in consts)


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialScala:
    def test_match_with_cases(self):
        source = """\
object M {
    val r = x match {
        case 1 => 10
        case 2 => 20
        case 3 => 30
        case _ => 0
    }
}
"""
        instructions = _parse_scala(source)
        opcodes = _opcodes(instructions)
        assert (
            Opcode.BRANCH_IF in opcodes
        ), "match with cases must produce BRANCH_IF for dispatch"
        labels = _labels_in_order(instructions)
        case_labels = [lbl for lbl in labels if "case" in lbl]
        assert (
            len(case_labels) >= 3
        ), "4 cases (3 concrete + 1 default) should produce >= 3 case labels"
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)
        assert len(instructions) > 15

    def test_object_with_method(self):
        source = """\
object Utils {
    def double(x: Int): Int = x + x
    def triple(x: Int): Int = x + x + x
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Utils" in inst.operands for inst in stores)
        assert any("double" in inst.operands for inst in stores)
        assert any("triple" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 2

    def test_class_with_constructor_and_method(self):
        source = """\
class Counter(start: Int) {
    var count: Int = start
    def increment(): Unit = {
        count = count + 1
    }
    def value(): Int = count
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        assert len(instructions) > 15

    def test_while_with_var_mutation(self):
        source = """\
object M {
    var i = 0
    var total = 0
    while (i < 10) {
        total = total + i
        i = i + 1
    }
}
"""
        instructions = _parse_scala(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        assert any("i" in inst.operands for inst in stores)
        labels = _labels_in_order(instructions)
        assert any("while" in lbl for lbl in labels)
        assert len(instructions) > 15

    def test_if_else_as_expression(self):
        source = """\
object M {
    val grade = if (score > 90) "A"
        else if (score > 70) "B"
        else "C"
}
"""
        instructions = _parse_scala(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("grade" in inst.operands for inst in stores)
        labels = _labels_in_order(instructions)
        assert any("if_true" in lbl for lbl in labels)

    def test_block_expression_returning_value(self):
        source = """\
object M {
    val result = {
        val a = 10
        val b = 20
        a + b
    }
}
"""
        instructions = _parse_scala(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)
        assert any("a" in inst.operands for inst in stores)
        assert any("b" in inst.operands for inst in stores)

    def test_val_and_var_with_computation(self):
        source = """\
object M {
    val x = 10
    val y = 20
    var z = x + y
    z = z * 2
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        assert any("y" in inst.operands for inst in stores)
        assert any("z" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        operators = [inst.operands[0] for inst in binops if inst.operands]
        assert "+" in operators
        assert "*" in operators

    def test_function_calling_function(self):
        source = """\
object M {
    def inc(x: Int): Int = x + 1
    def double_inc(x: Int): Int = {
        val a = inc(x)
        inc(a)
    }
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("inc" in inst.operands for inst in stores)
        assert any("double_inc" in inst.operands for inst in stores)
        all_calls = _find_all(instructions, Opcode.CALL_FUNCTION) + _find_all(
            instructions, Opcode.CALL_UNKNOWN
        )
        assert len(all_calls) >= 2
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 2


class TestScalaForExpression:
    def test_for_comprehension_basic(self):
        source = """\
object M {
    for (x <- List(1, 2, 3)) yield x
}
"""
        instructions = _parse_scala(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        iter_calls = [c for c in calls if "iter" in c.operands]
        assert len(iter_calls) >= 1
        labels = _labels_in_order(instructions)
        assert any("for_comp" in lbl for lbl in labels)

    def test_for_comprehension_with_body(self):
        source = """\
object M {
    for (x <- items) {
        println(x)
    }
}
"""
        instructions = _parse_scala(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("iter" in inst.operands for inst in calls)
        assert any("next" in inst.operands for inst in calls)

    def test_for_comprehension_stores_binding(self):
        source = """\
object M {
    for (item <- collection) yield item
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("item" in inst.operands for inst in stores)


class TestScalaTraitDefinition:
    def test_trait_produces_class_ref(self):
        source = """\
trait Animal {
    def speak(): String
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Animal" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_trait_with_method(self):
        source = """\
trait Greeter {
    def greet(name: String): String = "Hello " + name
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Greeter" in inst.operands for inst in stores)
        assert any("greet" in inst.operands for inst in stores)

    def test_trait_labels(self):
        source = "trait Foo { val x = 1 }"
        instructions = _parse_scala(source)
        labels = _labels_in_order(instructions)
        assert any("class_Foo" in lbl for lbl in labels)
        assert any("end_class_Foo" in lbl for lbl in labels)


class TestScalaCaseClassDefinition:
    def test_case_class_produces_class_ref(self):
        source = "case class Point(x: Int, y: Int)"
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Point" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)

    def test_case_class_with_body(self):
        source = """\
case class Person(name: String, age: Int) {
    def greeting(): String = "Hi, " + name
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Person" in inst.operands for inst in stores)
        assert any("greeting" in inst.operands for inst in stores)


class TestScalaLazyValDefinition:
    def test_lazy_val_produces_store_var(self):
        source = "object M { lazy val x = 42 }"
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)

    def test_lazy_val_with_expression(self):
        source = "object M { lazy val computed = 10 + 20 }"
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("computed" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestScalaDoWhileExpression:
    def test_do_while_basic(self):
        source = """\
object M {
    var x = 10
    do {
        x = x - 1
    } while (x > 0)
}
"""
        instructions = _parse_scala(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _labels_in_order(instructions)
        assert any("do_body" in lbl for lbl in labels)
        assert any("do_end" in lbl for lbl in labels)

    def test_do_while_stores_var(self):
        source = """\
object M {
    var count = 0
    do {
        count = count + 1
    } while (count < 5)
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("count" in inst.operands for inst in stores)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestScalaThrowExpression:
    def test_throw_emits_throw_opcode(self):
        source = 'object M { throw new Exception("error") }'
        instructions = _parse_scala(source)
        opcodes = _opcodes(instructions)
        assert Opcode.THROW in opcodes
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("throw_expression" in str(inst.operands) for inst in symbolics)

    def test_throw_with_variable(self):
        source = "object M { val e = new RuntimeException(); throw e }"
        instructions = _parse_scala(source)
        opcodes = _opcodes(instructions)
        assert Opcode.THROW in opcodes

    def test_throw_in_if_expression(self):
        source = """\
object M {
    val x = if (cond) 42 else throw new IllegalStateException("bad")
}
"""
        instructions = _parse_scala(source)
        opcodes = _opcodes(instructions)
        assert Opcode.THROW in opcodes
        assert Opcode.BRANCH_IF in opcodes


class TestScalaInstanceExpression:
    def test_new_expression_no_symbolic(self):
        source = 'object M { val x = new Exception("test") }'
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "instance_expression" in str(inst.operands) for inst in symbolics
        )
        assert not any("new_expression" in str(inst.operands) for inst in symbolics)

    def test_new_expression_produces_call(self):
        source = "object M { val dog = new Dog() }"
        instructions = _parse_scala(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert len(calls) >= 1

    def test_new_expression_stored(self):
        source = 'object M { val msg = new String("hello") }'
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("msg" in inst.operands for inst in stores)


class TestScalaOperatorPrecedenceBug:
    """Document tree-sitter Scala grammar operator precedence bug.

    Tree-sitter's Scala grammar uses a flat ``infix_expression`` with
    ``operator_identifier`` for ALL binary operators, ignoring Scala's
    actual precedence rules.  This means ``j < n - 1`` is parsed as
    ``(j < n) - 1`` instead of ``j < (n - 1)``.

    Other language grammars (Java, Kotlin, Rust, etc.) use distinct node
    types for comparison vs arithmetic (e.g. ``comparison_expression`` vs
    ``additive_expression``), so they parse correctly.

    This is an upstream tree-sitter-scala limitation, not a RedDragon
    frontend bug.  Fixing it would require implementing a precedence-
    climbing re-association pass on top of the flat AST.
    """

    @pytest.mark.xfail(
        reason="tree-sitter Scala grammar lacks operator precedence",
        strict=True,
    )
    def test_comparison_lower_precedence_than_subtraction(self):
        """``j < n - 1`` should parse as ``j < (n - 1)``, not ``(j < n) - 1``."""
        instructions = _parse_scala("object M { val r = j < n - 1 }")
        binops = _find_all(instructions, Opcode.BINOP)
        # Correct precedence: subtraction first, comparison second.
        # The last BINOP emitted should be the comparison ``<``.
        assert len(binops) == 2
        assert (
            binops[0].operands[0] == "-"
        ), f"expected first binop to be '-', got '{binops[0].operands[0]}'"
        assert (
            binops[1].operands[0] == "<"
        ), f"expected second binop to be '<', got '{binops[1].operands[0]}'"

    @pytest.mark.xfail(
        reason="tree-sitter Scala grammar lacks operator precedence",
        strict=True,
    )
    def test_mixed_arithmetic_and_comparison(self):
        """``a + b > c * d`` should compare the sum against the product."""
        instructions = _parse_scala("object M { val r = a + b > c * d }")
        binops = _find_all(instructions, Opcode.BINOP)
        ops = [inst.operands[0] for inst in binops]
        # Correct order: +, *, then >
        assert ops == ["+", "*", ">"], f"expected ['+', '*', '>'], got {ops}"


class TestScalaTypeDefinition:
    def test_type_alias_is_noop(self):
        source = "object M { type Alias = List[Int] }"
        instructions = _parse_scala(source)
        # Type definition should be a no-op lambda, not crash
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"


class TestScalaStringInterpolation:
    def test_interpolation_basic(self):
        instructions = _parse_scala('val s = s"Hello $name"')
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("name" in inst.operands for inst in loads)

    def test_interpolation_expression(self):
        instructions = _parse_scala('val s = s"${x + 1}"')
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_interpolation_multiple(self):
        instructions = _parse_scala('val s = s"$a and $b"')
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        load_names = [inst.operands[0] for inst in loads]
        assert "a" in load_names
        assert "b" in load_names
        binops = _find_all(instructions, Opcode.BINOP)
        concat_ops = [inst for inst in binops if inst.operands[0] == "+"]
        assert len(concat_ops) >= 2

    def test_no_interpolation_is_const(self):
        instructions = _parse_scala('val s = "hello"')
        consts = _find_all(instructions, Opcode.CONST)
        assert len(consts) >= 1
        # No BINOP for plain string
        binops = _find_all(instructions, Opcode.BINOP)
        assert not binops


class TestScalaDestructuring:
    def test_val_tuple_destructure_two_elements(self):
        instructions = _parse_scala("object M { val (a, b) = getPair() }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "a" in store_names
        assert "b" in store_names
        load_indices = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_indices) >= 2

    def test_val_tuple_destructure_three_elements(self):
        instructions = _parse_scala("object M { val (x, y, z) = getTriple() }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "x" in store_names
        assert "y" in store_names
        assert "z" in store_names
        load_indices = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_indices) >= 3

    def test_var_tuple_destructure(self):
        instructions = _parse_scala("object M { var (first, second) = split() }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "first" in store_names
        assert "second" in store_names
        load_indices = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_indices) >= 2


class TestScalaCaseClassPattern:
    def test_case_class_pattern_no_symbolic(self):
        source = "object M { def f(s: Any) = s match { case Circle(r) => r } }"
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("case_class_pattern" in str(inst.operands) for inst in symbolics)

    def test_case_class_pattern_new_object(self):
        source = "object M { def f(s: Any) = s match { case Circle(r) => r } }"
        instructions = _parse_scala(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("Circle" in str(inst.operands) for inst in new_objs)


class TestScalaFunctionDeclaration:
    def test_function_declaration_no_symbolic(self):
        source = "trait Shape { def area(): Double }"
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "function_declaration" in str(inst.operands) for inst in symbolics
        )

    def test_function_declaration_stores(self):
        source = "trait Shape { def area(): Double }"
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("area" in inst.operands for inst in stores)


class TestScalaTypedPattern:
    def test_typed_pattern_no_symbolic(self):
        source = "object M { def f(x: Any) = x match { case i: Int => i } }"
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("typed_pattern" in str(inst.operands) for inst in symbolics)


class TestScalaGuard:
    def test_guard_no_symbolic(self):
        source = "object M { def f(x: Int) = x match { case n if n > 0 => n } }"
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:guard" in str(inst.operands) for inst in symbolics)


class TestScalaTuplePatternMatch:
    def test_tuple_pattern_no_symbolic(self):
        source = "object M { def f(t: Any) = t match { case (a, b) => a } }"
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:tuple_pattern" in str(inst.operands) for inst in symbolics
        )


class TestScalaOperatorIdentifier:
    def test_operator_identifier_no_symbolic(self):
        source = "object M { val x = List(1, 2, 3).reduce(_ + _) }"
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "operator_identifier" in str(inst.operands) for inst in symbolics
        )


class TestScalaArguments:
    def test_arguments_no_symbolic(self):
        source = "object M { val s = Set(1, 2, 3) }"
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("arguments" in str(inst.operands) for inst in symbolics)


class TestScalaCaseBlock:
    def test_case_block_no_unsupported(self):
        """case block in match should not produce unsupported SYMBOLIC."""
        source = """\
object M {
    val r = x match {
        case 1 => "one"
        case 2 => "two"
        case _ => "other"
    }
}
"""
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_case_block_produces_branches(self):
        source = """\
object M {
    val r = x match {
        case 1 => "one"
        case _ => "other"
    }
}
"""
        instructions = _parse_scala(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes, "case block must produce BRANCH_IF"


class TestScalaInfixPattern:
    def test_infix_pattern_no_unsupported(self):
        """list match { case head :: tail => head } should not produce unsupported SYMBOLIC."""
        source = """\
object M {
    def f(list: Any) = list match {
        case head :: tail => head
        case _ => null
    }
}
"""
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_infix_pattern_with_nested(self):
        source = """\
object M {
    def f(xs: Any) = xs match {
        case a :: b :: Nil => a
        case _ => 0
    }
}
"""
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestScalaTryCatch:
    def test_try_catch_generates_caught_exception(self):
        """Scala catch { case e: Exception => ... } should lower to
        SYMBOLIC caught_exception, not be silently dropped."""
        source = """\
object M {
    var answer: Int = 0
    try {
        answer = -1
    } catch {
        case e: Exception => answer = 99
    }
}
"""
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        caught = [
            s
            for s in symbolics
            if any("caught_exception" in str(op) for op in s.operands)
        ]
        assert len(caught) >= 1, (
            "Expected at least 1 SYMBOLIC caught_exception from catch clause, "
            f"got {len(caught)}"
        )

    def test_try_catch_stores_exception_variable(self):
        """The exception variable 'e' should be stored via STORE_VAR."""
        source = """\
object M {
    try {
        val x = 1
    } catch {
        case e: Exception => val y = 2
    }
}
"""
        instructions = _parse_scala(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        stored_names = [inst.operands[0] for inst in stores]
        assert (
            "e" in stored_names
        ), f"Expected 'e' in stored variables, got {stored_names}"

    def test_try_catch_has_branch_to_end(self):
        """Try body should BRANCH past the catch block to try_end."""
        source = """\
object M {
    try {
        val x = 1
    } catch {
        case e: Exception => val y = 2
    }
}
"""
        instructions = _parse_scala(source)
        labels = _find_all(instructions, Opcode.LABEL)
        try_end_labels = [l for l in labels if "try_end" in l.label]
        assert len(try_end_labels) >= 1, "Expected at least 1 try_end label in IR"

    def test_try_catch_with_finally(self):
        """Scala try/catch/finally should generate all three blocks."""
        source = """\
object M {
    var answer: Int = 0
    try {
        answer = 1
    } catch {
        case e: Exception => answer = 2
    } finally {
        answer = 3
    }
}
"""
        instructions = _parse_scala(source)
        labels = _find_all(instructions, Opcode.LABEL)
        label_names = [l.label for l in labels]
        assert any("try_body" in name for name in label_names)
        assert any("catch" in name for name in label_names)
        assert any("try_finally" in name for name in label_names)
        assert any("try_end" in name for name in label_names)

    def test_try_catch_multiple_cases(self):
        """Multiple case clauses should generate multiple catch blocks."""
        source = """\
object M {
    try {
        val x = 1
    } catch {
        case e: IllegalArgumentException => val a = 1
        case e: RuntimeException => val b = 2
    }
}
"""
        instructions = _parse_scala(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        caught = [
            s
            for s in symbolics
            if any("caught_exception" in str(op) for op in s.operands)
        ]
        assert len(caught) >= 2, (
            "Expected at least 2 SYMBOLIC caught_exception (one per case clause), "
            f"got {len(caught)}"
        )


class TestScalaGenericTypeSeeding:
    """Verify that Scala generic types (List[String], Map[K,V]) are extracted
    as parameterised bracket-notation strings in the TypeEnvironmentBuilder."""

    def test_val_list_of_string(self):
        """val items: List[String] = ... should seed var_types['items'] = 'List[String]'."""
        source = 'object M { val items: List[String] = List("a") }'
        _, builder = _parse_scala_with_types(source)
        assert builder.var_types["items"] == "List[String]"

    def test_val_map_of_string_int(self):
        """val m: Map[String, Int] = ... should seed 'Map[String, Int]'."""
        source = "object M { val m: Map[String, Int] = Map() }"
        _, builder = _parse_scala_with_types(source)
        assert builder.var_types["m"] == "Map[String, Int]"

    def test_nested_generic_type(self):
        """List[Map[String, Int]] should produce 'List[Map[String, Int]]'."""
        source = "object M { val x: List[Map[String, Int]] = List() }"
        _, builder = _parse_scala_with_types(source)
        assert builder.var_types["x"] == "List[Map[String, Int]]"

    def test_def_return_generic_type(self):
        """def getNames: List[String] should seed func_return_types with 'List[String]'."""
        source = 'object M { def getNames: List[String] = List("a") }'
        _, builder = _parse_scala_with_types(source)
        return_types = builder.func_return_types
        assert any(v == "List[String]" for v in return_types.values())

    def test_param_generic_type(self):
        """Parameter items: List[String] should seed param type 'List[String]'."""
        source = "object M { def process(items: List[String]): Unit = {} }"
        _, builder = _parse_scala_with_types(source)
        param_types = builder.func_param_types
        assert any(
            any(ptype == "List[String]" for _, ptype in params)
            for params in param_types.values()
        )

    def test_non_generic_type_unchanged(self):
        """val x: Int = 42 should still seed 'Int' (regression check)."""
        source = "object M { val x: Int = 42 }"
        _, builder = _parse_scala_with_types(source)
        assert builder.var_types["x"] == "Int"


class TestScalaExportDeclaration:
    def test_export_no_symbolic(self):
        """export foo._ should not produce SYMBOLIC fallthrough."""
        ir = _parse_scala("export foo._\nval x = 42")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("export_declaration" in str(inst.operands) for inst in symbolics)

    def test_export_does_not_block(self):
        """Code after export should still be lowered."""
        ir = _parse_scala("export foo._\nval x = 42")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestScalaValDeclaration:
    def test_val_declaration_no_symbolic(self):
        """val x: Int (no body) should not produce SYMBOLIC."""
        ir = _parse_scala("trait Foo { val x: Int }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("val_declaration" in str(inst.operands) for inst in symbolics)

    def test_val_declaration_does_not_block(self):
        """Code after val declaration should be lowered."""
        ir = _parse_scala("trait Foo { val x: Int }\nval y = 42")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)


class TestScalaAlternativePattern:
    def test_alternative_pattern_no_symbolic(self):
        """case A | B => should not produce SYMBOLIC."""
        code = """\
val x = 1
x match {
  case 1 | 2 => val r = 10
  case _ => val r = 0
}"""
        ir = _parse_scala(code)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "alternative_pattern" in str(inst.operands) for inst in symbolics
        )


class TestScalaArrayIndexing:
    """Scala arr(i) uses CALL_FUNCTION (syntactically ambiguous with function calls).

    The VM resolves arr(i) to native indexing when the target is a list.
    arr(i) = 5 on the LHS of assignment emits STORE_INDEX at the frontend level.
    """

    def test_arr_read_emits_call_function(self):
        """arr(i) is syntactically identical to f(i) in Scala — emits CALL_FUNCTION."""
        ir = _parse_scala("""\
object M {
    val arr = Array(1, 2, 3)
    var i = 1
    val x = arr(i)
}""")
        calls = [inst for inst in ir if inst.opcode == Opcode.CALL_FUNCTION]
        arr_calls = [c for c in calls if c.operands and c.operands[0] == "arr"]
        assert (
            len(arr_calls) >= 1
        ), "Expected CALL_FUNCTION for arr(i) — VM resolves to indexing at runtime"

    def test_arr_write_emits_store_index(self):
        ir = _parse_scala("""\
object M {
    var arr = Array(1, 2, 3)
    arr(1) = 5
}""")
        store_indices = _find_all(ir, Opcode.STORE_INDEX)
        assert len(store_indices) >= 1, "Expected STORE_INDEX for arr(1) = 5, got none"

    def test_array_accumulate_execution(self):
        """Scala array accumulation via CALL_FUNCTION resolved by VM to indexing."""
        from tests.unit.rosetta.conftest import execute_for_language, extract_answer

        vm, stats = execute_for_language(
            "scala",
            """\
object M {
    val arr = Array(1, 2, 3, 4, 5)
    var answer = 0
    var i = 0
    while (i < 5) {
        answer = answer + arr(i)
        i = i + 1
    }
}""",
        )
        assert extract_answer(vm, "scala") == 15
        assert stats.llm_calls == 0
