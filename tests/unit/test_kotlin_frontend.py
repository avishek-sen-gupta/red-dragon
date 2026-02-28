"""Tests for KotlinFrontend -- tree-sitter Kotlin AST to IR lowering."""

from __future__ import annotations

from tree_sitter_language_pack import get_parser

from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.ir import IRInstruction, Opcode
from tests.unit.rosetta.conftest import execute_for_language, extract_answer


def _parse_kotlin(source: str) -> list[IRInstruction]:
    parser = get_parser("kotlin")
    tree = parser.parse(source.encode("utf-8"))
    frontend = KotlinFrontend()
    return frontend.lower(tree, source.encode("utf-8"))


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestKotlinDeclarations:
    def test_val_declaration(self):
        instructions = _parse_kotlin("val x = 10")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_var_declaration(self):
        instructions = _parse_kotlin("var y = 5")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("y" in inst.operands for inst in stores)

    def test_val_without_initializer(self):
        instructions = _parse_kotlin("val x: Int")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestKotlinFunctions:
    def test_function_declaration(self):
        instructions = _parse_kotlin("fun add(a: Int, b: Int): Int { return a + b }")
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
        instructions = _parse_kotlin("fun main() { add(1, 2) }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("add" in inst.operands for inst in calls)

    def test_return_via_jump_expression(self):
        instructions = _parse_kotlin("fun main() { return 42 }")
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestKotlinControlFlow:
    def test_if_expression(self):
        instructions = _parse_kotlin("fun main() { val y = if (x > 0) 1 else 0 }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.LABEL in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("if_true" in (inst.label or "") for inst in labels)

    def test_while_loop(self):
        instructions = _parse_kotlin("fun main() { while (x > 0) { x = x - 1 } }")
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("while" in (inst.label or "") for inst in labels)

    def test_when_expression(self):
        instructions = _parse_kotlin(
            "fun main() { val r = when (x) { 1 -> 10\n 2 -> 20\n else -> 0 } }"
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("when" in (inst.label or "") for inst in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)


class TestKotlinClasses:
    def test_class_declaration(self):
        instructions = _parse_kotlin(
            'class Dog { fun bark(): String { return "woof" } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)


class TestKotlinExpressions:
    def test_navigation_expression_member_access(self):
        instructions = _parse_kotlin("fun main() { val f = obj.name }")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_FIELD in opcodes
        fields = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("name" in str(inst.operands) for inst in fields)

    def test_additive_binary_op(self):
        instructions = _parse_kotlin("fun main() { val z = x + y }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_multiplicative_binary_op(self):
        instructions = _parse_kotlin("fun main() { val z = x * y }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("*" in inst.operands for inst in binops)

    def test_comparison_binary_op(self):
        instructions = _parse_kotlin("fun main() { val b = x > y }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any(">" in inst.operands for inst in binops)

    def test_string_literal(self):
        instructions = _parse_kotlin('fun main() { val s = "hello" }')
        consts = _find_all(instructions, Opcode.CONST)
        assert any('"hello"' in inst.operands for inst in consts)

    def test_null_literal(self):
        instructions = _parse_kotlin("fun main() { val n = null }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("None" in inst.operands for inst in consts)


class TestKotlinSpecial:
    def test_empty_program(self):
        instructions = _parse_kotlin("")
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[0].label == "entry"

    def test_fallback_symbolic(self):
        instructions = _parse_kotlin("fun main() { @Deprecated fun old() {} }")
        opcodes = _opcodes(instructions)
        # Should produce at least some IR; annotation itself might be ignored
        assert len(instructions) > 1

    def test_method_call_via_navigation(self):
        instructions = _parse_kotlin("fun main() { obj.doSomething(1) }")
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("doSomething" in str(inst.operands) for inst in calls)

    def test_lambda_literal(self):
        instructions = _parse_kotlin(
            "fun main() { val f = { a: Int, b: Int -> a + b } }"
        )
        consts = _find_all(instructions, Opcode.CONST)
        assert any("__lambda" in str(inst.operands) for inst in consts)


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialKotlin:
    def test_when_with_multiple_branches(self):
        source = """\
fun main() {
    val r = when (x) {
        1 -> 10
        2 -> 20
        3 -> 30
        4 -> 40
        else -> 0
    }
}
"""
        instructions = _parse_kotlin(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 4
        labels = _labels_in_order(instructions)
        assert any("when" in lbl for lbl in labels)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)
        assert len(instructions) > 20

    def test_lambda_in_method_call(self):
        source = """\
fun main() {
    val doubled = items.map { it * 2 }
}
"""
        instructions = _parse_kotlin(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("map" in str(inst.operands) for inst in calls)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("doubled" in inst.operands for inst in stores)

    def test_class_with_method_and_property(self):
        source = """\
class Counter {
    var count: Int = 0
    fun increment() {
        count = count + 1
    }
    fun value(): Int {
        return count
    }
}
"""
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1
        assert len(instructions) > 15

    def test_for_loop_with_conditional(self):
        source = """\
fun main() {
    var total = 0
    for (item in items) {
        if (item > 10) {
            total = total + item
        }
    }
}
"""
        instructions = _parse_kotlin(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("total" in inst.operands for inst in stores)
        assert len(instructions) > 15

    def test_if_expression_as_value(self):
        source = """\
fun main() {
    val grade = if (score > 90) "A"
        else if (score > 70) "B"
        else if (score > 50) "C"
        else "F"
}
"""
        instructions = _parse_kotlin(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 3
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("grade" in inst.operands for inst in stores)
        labels = _labels_in_order(instructions)
        assert any("if_true" in lbl for lbl in labels)

    def test_while_with_when_inside(self):
        source = """\
fun main() {
    var i = 0
    while (i < 10) {
        val label = when {
            i > 5 -> "high"
            else -> "low"
        }
        i = i + 1
    }
}
"""
        instructions = _parse_kotlin(source)
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        labels = _labels_in_order(instructions)
        assert any("while" in lbl for lbl in labels)
        assert len(instructions) > 15

    def test_extension_function(self):
        source = """\
fun Int.double(): Int {
    return this * 2
}
"""
        instructions = _parse_kotlin(source)
        opcodes = _opcodes(instructions)
        assert Opcode.RETURN in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("*" in inst.operands for inst in binops)

    def test_null_safety_navigation(self):
        source = """\
fun main() {
    val name = user?.name
    val upper = name?.toUpperCase()
}
"""
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("name" in inst.operands for inst in stores)
        assert any("upper" in inst.operands for inst in stores)
        assert len(instructions) > 3


class TestKotlinNotNullAssertion:
    def test_not_null_assertion_produces_unop(self):
        instructions = _parse_kotlin("fun main() { val x = y!! }")
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("!!" in inst.operands for inst in unops)

    def test_not_null_assertion_on_member(self):
        instructions = _parse_kotlin("fun main() { val x = obj.value!! }")
        unops = _find_all(instructions, Opcode.UNOP)
        assert any("!!" in inst.operands for inst in unops)


class TestKotlinCheckExpression:
    def test_is_check_produces_call_function(self):
        instructions = _parse_kotlin("fun main() { val b = x is String }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("is" in inst.operands for inst in calls)

    def test_is_check_includes_type(self):
        instructions = _parse_kotlin("fun main() { val b = x is Int }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        is_calls = [c for c in calls if "is" in c.operands]
        assert any("Int" in str(inst.operands) for inst in is_calls)

    def test_is_check_in_when(self):
        source = """\
fun main() {
    val result = when {
        x is String -> "string"
        x is Int -> "int"
        else -> "other"
    }
}
"""
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("result" in inst.operands for inst in stores)


class TestKotlinDoWhile:
    def test_do_while_produces_labels_and_branch(self):
        instructions = _parse_kotlin(
            "fun main() { var i = 0; do { i = i + 1 } while (i < 10) }"
        )
        labels = _labels_in_order(instructions)
        assert any("do_body" in lbl for lbl in labels)
        assert any("do_end" in lbl for lbl in labels)

    def test_do_while_has_branch_if(self):
        instructions = _parse_kotlin(
            "fun main() { var i = 0; do { i = i + 1 } while (i < 10) }"
        )
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 1

    def test_do_while_body_executes_first(self):
        instructions = _parse_kotlin("fun main() { do { x = 1 } while (false) }")
        # Body should produce STORE_VAR before the BRANCH_IF
        store_idx = next(
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.STORE_VAR and "x" in inst.operands
        )
        branch_idx = next(
            i for i, inst in enumerate(instructions) if inst.opcode == Opcode.BRANCH_IF
        )
        assert store_idx < branch_idx


class TestKotlinObjectDeclaration:
    def test_object_declaration_produces_new_object(self):
        instructions = _parse_kotlin("object Singleton { val x = 10 }")
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("Singleton" in inst.operands for inst in new_objs)

    def test_object_declaration_stores_var(self):
        instructions = _parse_kotlin("object Config { val debug = true }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Config" in inst.operands for inst in stores)

    def test_object_declaration_body_lowered(self):
        instructions = _parse_kotlin("object Logger { fun log() { return } }")
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1


class TestKotlinCompanionObject:
    def test_companion_object_body_lowered(self):
        source = """\
class MyClass {
    companion object {
        val DEFAULT = 42
    }
}
"""
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("MyClass" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)

    def test_companion_with_method(self):
        source = """\
class Factory {
    companion object {
        fun create(): Factory { return Factory() }
    }
}
"""
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Factory" in inst.operands for inst in stores)


class TestKotlinEnumClassBody:
    def test_enum_entries_produce_new_object(self):
        source = """\
enum class Color {
    RED,
    GREEN,
    BLUE
}
"""
        instructions = _parse_kotlin(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        obj_names = [str(inst.operands) for inst in new_objs]
        assert any("enum:RED" in name for name in obj_names)
        assert any("enum:GREEN" in name for name in obj_names)
        assert any("enum:BLUE" in name for name in obj_names)

    def test_enum_entries_stored_as_vars(self):
        source = """\
enum class Direction {
    NORTH,
    SOUTH
}
"""
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("NORTH" in inst.operands for inst in stores)
        assert any("SOUTH" in inst.operands for inst in stores)

    def test_enum_class_stored(self):
        source = """\
enum class Status {
    ACTIVE,
    INACTIVE
}
"""
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("Status" in inst.operands for inst in stores)


class TestKotlinTypeAlias:
    def test_type_alias_is_noop(self):
        instructions = _parse_kotlin("typealias Name = String")
        # Should not produce any meaningful IR beyond entry label
        opcodes = _opcodes(instructions)
        assert Opcode.LABEL in opcodes
        # Should not crash

    def test_type_alias_does_not_produce_store(self):
        instructions = _parse_kotlin("typealias StringList = List<String>")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert len(stores) == 0


class TestKotlinConjunctionDisjunction:
    def test_conjunction_expression(self):
        instructions = _parse_kotlin("fun main() { val b = x && y }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("&&" in inst.operands for inst in binops)

    def test_disjunction_expression(self):
        instructions = _parse_kotlin("fun main() { val b = x || y }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("||" in inst.operands for inst in binops)

    def test_conjunction_not_symbolic(self):
        """conjunction_expression should produce BINOP, not SYMBOLIC."""
        instructions = _parse_kotlin("fun main() { val b = a && b }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("conjunction" in str(inst.operands) for inst in symbolics)


class TestKotlinHexLiteral:
    def test_hex_literal_basic(self):
        instructions = _parse_kotlin("fun main() { val x = 0xFF }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("0xFF" in inst.operands for inst in consts)

    def test_hex_literal_not_symbolic(self):
        instructions = _parse_kotlin("fun main() { val x = 0x1A2B }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("hex_literal" in str(inst.operands) for inst in symbolics)

    def test_hex_literal_in_expression(self):
        instructions = _parse_kotlin("fun main() { val x = 0xFF + 1 }")
        consts = _find_all(instructions, Opcode.CONST)
        assert any("0xFF" in inst.operands for inst in consts)
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestKotlinElvisExpression:
    def test_elvis_basic(self):
        instructions = _parse_kotlin("fun main() { val x = y ?: 0 }")
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("?:" in inst.operands for inst in binops)

    def test_elvis_stores_result(self):
        instructions = _parse_kotlin('fun main() { val x = name ?: "default" }')
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_elvis_not_symbolic(self):
        instructions = _parse_kotlin("fun main() { val x = y ?: z }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("elvis" in str(inst.operands) for inst in symbolics)


class TestKotlinInfixExpression:
    def test_infix_to(self):
        instructions = _parse_kotlin("fun main() { val r = 1 to 10 }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("to" in inst.operands for inst in calls)

    def test_infix_until(self):
        instructions = _parse_kotlin("fun main() { val r = 1 until 10 }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("until" in inst.operands for inst in calls)

    def test_infix_stores_result(self):
        instructions = _parse_kotlin("fun main() { val r = 1 to 10 }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("r" in inst.operands for inst in stores)


class TestKotlinIndexingExpression:
    def test_indexing_basic(self):
        instructions = _parse_kotlin("fun main() { val x = list[0] }")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes

    def test_indexing_with_variable(self):
        instructions = _parse_kotlin("fun main() { val x = map[key] }")
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_INDEX in opcodes

    def test_indexing_stores_result(self):
        instructions = _parse_kotlin("fun main() { val x = arr[0] }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestKotlinAsExpression:
    def test_as_basic(self):
        instructions = _parse_kotlin("fun main() { val x = y as Int }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("as" in inst.operands for inst in calls)
        assert any("Int" in str(inst.operands) for inst in calls)

    def test_as_stores_result(self):
        instructions = _parse_kotlin("fun main() { val x = obj as String }")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_as_not_symbolic(self):
        instructions = _parse_kotlin("fun main() { val x = y as Int }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("as_expression" in str(inst.operands) for inst in symbolics)


class TestKotlinOperatorExecution:
    """VM execution tests for Kotlin-specific operators."""

    def test_not_null_assertion(self):
        source = """\
fun identity(x: Int): Int {
    return x!!
}

val answer = identity(42)
"""
        vm, stats = execute_for_language("kotlin", source)
        assert extract_answer(vm, "kotlin") == 42
        assert stats.llm_calls == 0

    def test_elvis_with_null(self):
        source = """\
val x: Int? = null
val answer = x ?: 99
"""
        vm, stats = execute_for_language("kotlin", source)
        assert extract_answer(vm, "kotlin") == 99
        assert stats.llm_calls == 0

    def test_elvis_with_non_null(self):
        source = """\
val x: Int? = 42
val answer = x ?: 99
"""
        vm, stats = execute_for_language("kotlin", source)
        assert extract_answer(vm, "kotlin") == 42
        assert stats.llm_calls == 0


class TestKotlinStringInterpolation:
    def test_interpolation_basic(self):
        instructions = _parse_kotlin('"Hello $name"')
        opcodes = _opcodes(instructions)
        assert Opcode.LOAD_VAR in opcodes
        assert Opcode.BINOP in opcodes
        assert Opcode.SYMBOLIC not in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        assert any("name" in inst.operands for inst in loads)

    def test_interpolation_expression(self):
        instructions = _parse_kotlin('"${x + 1}"')
        opcodes = _opcodes(instructions)
        assert Opcode.BINOP in opcodes
        binops = _find_all(instructions, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_interpolation_multiple(self):
        instructions = _parse_kotlin('"$a and $b"')
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        load_names = [inst.operands[0] for inst in loads]
        assert "a" in load_names
        assert "b" in load_names
        binops = _find_all(instructions, Opcode.BINOP)
        concat_ops = [inst for inst in binops if inst.operands[0] == "+"]
        assert len(concat_ops) >= 2

    def test_no_interpolation_is_const(self):
        instructions = _parse_kotlin('"hello"')
        consts = _find_all(instructions, Opcode.CONST)
        assert len(consts) >= 1
        binops = _find_all(instructions, Opcode.BINOP)
        assert not binops


class TestKotlinDestructuring:
    def test_destructure_two_elements(self):
        instructions = _parse_kotlin("val (a, b) = pair")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "a" in store_names
        assert "b" in store_names
        load_indices = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_indices) >= 2

    def test_destructure_three_elements(self):
        instructions = _parse_kotlin("val (x, y, z) = triple")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "x" in store_names
        assert "y" in store_names
        assert "z" in store_names
        load_indices = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_indices) >= 3

    def test_destructure_with_usage(self):
        source = "val (first, second) = getPair()\nprintln(first)"
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.STORE_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "first" in store_names
        assert "second" in store_names


class TestKotlinRangeExpression:
    def test_range_expression_basic(self):
        instructions = _parse_kotlin("val r = 1..10")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("range_expression" in str(inst.operands) for inst in symbolics)

    def test_range_in_for_loop(self):
        instructions = _parse_kotlin("for (i in 1..10) { println(i) }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)

    def test_range_with_variables(self):
        instructions = _parse_kotlin("val r = start..end")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)
        loads = _find_all(instructions, Opcode.LOAD_VAR)
        load_names = [inst.operands[0] for inst in loads]
        assert "start" in load_names
        assert "end" in load_names


class TestKotlinObjectLiteral:
    def test_object_literal_produces_new_object(self):
        source = "val listener = object : OnClickListener {\n    fun onClick() { }\n}"
        instructions = _parse_kotlin(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert len(new_objs) >= 1
        assert any("OnClickListener" in inst.operands for inst in new_objs)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("object_literal" in str(inst.operands) for inst in symbolics)

    def test_object_literal_lowers_body(self):
        source = "val x = object : Runnable {\n    fun run() { println(42) }\n}"
        instructions = _parse_kotlin(source)
        opcodes = _opcodes(instructions)
        # Body function should be lowered (BRANCH + LABEL + RETURN pattern)
        assert Opcode.RETURN in opcodes
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert any("Runnable" in inst.operands for inst in new_objs)

    def test_object_literal_no_supertype(self):
        source = "val obj = object {\n    fun greet() { }\n}"
        instructions = _parse_kotlin(source)
        new_objs = _find_all(instructions, Opcode.NEW_OBJECT)
        assert len(new_objs) >= 1


class TestKotlinCharacterLiteral:
    def test_char_literal_no_symbolic(self):
        source = "val c = 'A'"
        instructions = _parse_kotlin(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("character_literal" in str(inst.operands) for inst in symbolics)

    def test_char_literal_as_const(self):
        source = "val c = 'Z'"
        instructions = _parse_kotlin(source)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("'Z'" in str(inst.operands) for inst in consts)


class TestKotlinLineComment:
    def test_line_comment_not_symbolic(self):
        source = "// this is a comment\nval x = 1"
        instructions = _parse_kotlin(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("line_comment" in str(inst.operands) for inst in symbolics)

    def test_line_comment_filtered(self):
        source = "val x = 1 // inline comment\nval y = 2"
        instructions = _parse_kotlin(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("line_comment" in str(inst.operands) for inst in symbolics)
