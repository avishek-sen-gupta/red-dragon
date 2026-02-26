"""Tests for ScalaFrontend -- tree-sitter Scala AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.scala import ScalaFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_scala(source: str) -> list[IRInstruction]:
    parser = get_parser("scala")
    tree = parser.parse(source.encode("utf-8"))
    frontend = ScalaFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


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
        assert Opcode.BRANCH_IF in opcodes or Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("case" in (inst.label or "") for inst in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)


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
        assert any("true" in inst.operands for inst in consts)


class TestScalaSpecial:
    def test_empty_program(self):
        instructions = _parse_scala("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_fallback_symbolic(self):
        instructions = _parse_scala("object M { type Alias = List[Int] }")
        opcodes = _opcodes(instructions)
        # Type alias should produce at least a SYMBOLIC or be passthrough
        assert len(instructions) > 1

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
        assert any("null" in inst.operands for inst in consts)


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
        assert Opcode.BRANCH_IF in opcodes or Opcode.BRANCH in opcodes
        labels = _labels_in_order(instructions)
        assert any("case" in lbl for lbl in labels)
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


class TestScalaTypeDefinition:
    def test_type_alias_is_noop(self):
        source = "object M { type Alias = List[Int] }"
        instructions = _parse_scala(source)
        # Type definition should be a no-op lambda, not crash
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"
