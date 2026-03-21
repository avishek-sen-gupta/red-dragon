"""Tests for KotlinFrontend -- tree-sitter Kotlin AST to IR lowering."""

from __future__ import annotations

from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment_builder import TypeEnvironmentBuilder
from tests.unit.rosetta.conftest import execute_for_language, extract_answer


def _parse_kotlin(source: str) -> list[IRInstruction]:
    frontend = KotlinFrontend(TreeSitterParserFactory(), "kotlin")
    return frontend.lower(source.encode("utf-8"))


def _parse_kotlin_with_types(
    source: str,
) -> tuple[list[IRInstruction], TypeEnvironmentBuilder]:
    frontend = KotlinFrontend(TreeSitterParserFactory(), "kotlin")
    instructions = frontend.lower(source.encode("utf-8"))
    return instructions, frontend.type_env_builder


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestKotlinDeclarations:
    def test_val_declaration(self):
        instructions = _parse_kotlin("val x = 10")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.DECL_VAR in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_var_declaration(self):
        instructions = _parse_kotlin("var y = 5")
        opcodes = _opcodes(instructions)
        assert Opcode.CONST in opcodes
        assert Opcode.DECL_VAR in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("y" in inst.operands for inst in stores)

    def test_val_without_initializer(self):
        instructions = _parse_kotlin("val x: Int")
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        assert any(
            "match" in (inst.label or "") or "when" in (inst.label or "")
            for inst in labels
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("r" in inst.operands for inst in stores)

    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/else-if/else-if/else must produce IR."""
        instructions = _parse_kotlin(
            "fun main() { if (x==1) { y=10 }"
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


class TestKotlinClasses:
    def test_class_declaration(self):
        instructions = _parse_kotlin(
            'class Dog { fun bark(): String { return "woof" } }'
        )
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH in opcodes
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Dog" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)


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

    def test_anonymous_function_no_longer_symbolic(self):
        """anonymous_function should now produce a function ref, not SYMBOLIC."""
        instructions = _parse_kotlin("fun main() { val x = fun(a: Int): Int = a + 1 }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("__anon_fun" in str(inst.operands) for inst in consts)

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
        assert any("match" in lbl or "when" in lbl for lbl in labels)
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Counter" in inst.operands for inst in stores)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("class_" in str(inst.operands) for inst in consts)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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

    def test_safe_navigation_lowering(self):
        """Kotlin ?. lowered as plain LOAD_FIELD/CALL_METHOD (null-check not in IR)."""
        source = """\
fun main() {
    val name = user?.name
    val upper = name?.toUpperCase()
}
"""
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("name" in inst.operands for inst in stores)
        assert any("upper" in inst.operands for inst in stores)
        # ?. lowered as field access + method call (no null-guard IR yet)
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("name" in inst.operands for inst in loads)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("toUpperCase" in inst.operands for inst in calls)
        assert len(instructions) > 5


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
        # `is` type checks produce CALL_FUNCTION with "is"
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("is" in inst.operands for inst in calls)
        # `when` arms produce BRANCH_IF for each condition
        opcodes = _opcodes(instructions)
        assert Opcode.BRANCH_IF in opcodes
        # Result is stored
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Factory" in inst.operands for inst in stores)
        # The `create` method must also be lowered
        assert any(
            "create" in inst.operands for inst in stores
        ), f"create method not stored, got {[s.operands for s in stores]}"


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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestKotlinAsExpression:
    def test_as_basic(self):
        instructions = _parse_kotlin("fun main() { val x = y as Int }")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("as" in inst.operands for inst in calls)
        assert any("Int" in str(inst.operands) for inst in calls)

    def test_as_stores_result(self):
        instructions = _parse_kotlin("fun main() { val x = obj as String }")
        stores = _find_all(instructions, Opcode.DECL_VAR)
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
        stores = _find_all(instructions, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "a" in store_names
        assert "b" in store_names
        load_indices = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_indices) >= 2

    def test_destructure_three_elements(self):
        instructions = _parse_kotlin("val (x, y, z) = triple")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        store_names = [inst.operands[0] for inst in stores]
        assert "x" in store_names
        assert "y" in store_names
        assert "z" in store_names
        load_indices = _find_all(instructions, Opcode.LOAD_INDEX)
        assert len(load_indices) >= 3

    def test_destructure_with_usage(self):
        source = "val (first, second) = getPair()\nprintln(first)"
        instructions = _parse_kotlin(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
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


class TestKotlinTypeTest:
    def test_type_test_no_symbolic(self):
        source = "fun f(x: Any) = when (x) {\n    is String -> x.length\n    is Int -> x\n    else -> 0\n}"
        instructions = _parse_kotlin(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("type_test" in str(inst.operands) for inst in symbolics)

    def test_type_test_isinstance_call(self):
        """is String in subject-when compiles to CALL_FUNCTION isinstance with type name."""
        source = "fun f(x: Any) = when (x) {\n    is String -> 1\n    else -> 0\n}"
        instructions = _parse_kotlin(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        consts = _find_all(instructions, Opcode.CONST)
        assert any("isinstance" in inst.operands for inst in calls)
        assert any("String" in str(inst.operands) for inst in consts)


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


class TestKotlinLabel:
    def test_label_no_unsupported(self):
        """outer@ for (i in 1..10) { break@outer } should not produce unsupported SYMBOLIC."""
        source = """\
fun main() {
    outer@ for (i in 1..10) {
        break@outer
    }
}
"""
        instructions = _parse_kotlin(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_label_with_continue(self):
        source = """\
fun main() {
    loop@ for (i in 1..10) {
        if (i == 5) continue@loop
    }
}
"""
        instructions = _parse_kotlin(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestKotlinGenericTypeSeeding:
    """Verify that Kotlin generic types (List<String>, Map<K,V>) are extracted
    as parameterised bracket-notation strings in the TypeEnvironmentBuilder."""

    def test_val_list_of_string(self):
        """val items: List<String> = ... should seed var_types['items'] = 'List[String]'."""
        source = 'fun main() { val items: List<String> = listOf("a") }'
        _, builder = _parse_kotlin_with_types(source)
        assert builder.var_types["items"] == "List[String]"

    def test_val_map_of_string_int(self):
        """val m: Map<String, Int> = ... should seed 'Map[String, Int]'."""
        source = "fun main() { val m: Map<String, Int> = mapOf() }"
        _, builder = _parse_kotlin_with_types(source)
        assert builder.var_types["m"] == "Map[String, Int]"

    def test_nested_generic_type(self):
        """List<Map<String, Int>> should produce 'List[Map[String, Int]]'."""
        source = "fun main() { val x: List<Map<String, Int>> = listOf() }"
        _, builder = _parse_kotlin_with_types(source)
        assert builder.var_types["x"] == "List[Map[String, Int]]"

    def test_fun_return_generic_type(self):
        """fun getNames(): List<String> should seed func_return_types with 'List[String]'."""
        source = 'fun getNames(): List<String> { return listOf("a") }'
        _, builder = _parse_kotlin_with_types(source)
        return_types = builder.func_return_types
        assert any(v == "List[String]" for v in return_types.values())

    def test_param_generic_type(self):
        """Parameter items: List<String> should seed param type 'List[String]'."""
        source = "fun process(items: List<String>) { }"
        _, builder = _parse_kotlin_with_types(source)
        param_types = builder.func_param_types
        assert any(
            any(ptype == "List[String]" for _, ptype in params)
            for params in param_types.values()
        )

    def test_non_generic_type_unchanged(self):
        """val x: Int = 42 should still seed 'Int' (regression check)."""
        source = "fun main() { val x: Int = 42 }"
        _, builder = _parse_kotlin_with_types(source)
        assert builder.var_types["x"] == "Int"


class TestKotlinThrowExpression:
    """P0 gap: throw as expression in elvis and other expression contexts."""

    def test_throw_in_elvis_no_symbolic(self):
        """val x = y ?: throw Exception('err') should lower without SYMBOLIC."""
        instructions = _parse_kotlin('val x = y ?: throw Exception("err")')
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_throw_in_elvis_emits_throw(self):
        """throw in elvis RHS should produce a THROW opcode."""
        instructions = _parse_kotlin('val x = y ?: throw Exception("err")')
        throws = _find_all(instructions, Opcode.THROW)
        assert len(throws) >= 1

    def test_throw_in_elvis_stores_result(self):
        """The val binding should still produce a STORE_VAR for x."""
        instructions = _parse_kotlin('val x = y ?: throw Exception("err")')
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_throw_in_elvis_calls_exception_constructor(self):
        """The Exception() constructor call should appear."""
        instructions = _parse_kotlin('val x = y ?: throw Exception("err")')
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("Exception" in inst.operands for inst in calls)


class TestKotlinWhenExpressionAsStatement:
    """P0 gap: when_expression used at statement level should be in stmt dispatch."""

    def test_when_stmt_no_symbolic(self):
        """when at statement level should not produce unsupported SYMBOLIC."""
        source = """\
fun main() {
    when(x) {
        1 -> println("one")
        2 -> println("two")
        else -> println("other")
    }
}
"""
        instructions = _parse_kotlin(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_when_stmt_produces_branch_if(self):
        """when at statement level should produce BRANCH_IF for each arm."""
        source = """\
fun main() {
    when(x) {
        1 -> println("one")
        2 -> println("two")
        else -> println("other")
    }
}
"""
        instructions = _parse_kotlin(source)
        branches = _find_all(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2

    def test_when_stmt_calls_println(self):
        """when arms should produce CALL_FUNCTION for println."""
        source = """\
fun main() {
    when(x) {
        1 -> println("one")
    }
}
"""
        instructions = _parse_kotlin(source)
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        assert any("println" in inst.operands for inst in calls)

    def test_when_stmt_in_dispatch_table(self):
        """when_expression should be in both expr and stmt dispatch tables."""
        frontend = KotlinFrontend(TreeSitterParserFactory(), "kotlin")
        # Force initialization by lowering empty program
        frontend.lower(b"")
        from interpreter.frontends.kotlin.node_types import KotlinNodeType as KNT

        assert KNT.WHEN_EXPRESSION in frontend._build_stmt_dispatch()


class TestKotlinAnonymousFunction:
    """P0 gap: anonymous_function (fun(x: Int): Int { ... }) should lower as function def."""

    def test_anonymous_function_no_symbolic(self):
        """fun(x: Int): Int { return x * 2 } should NOT produce unsupported SYMBOLIC."""
        instructions = _parse_kotlin(
            "fun main() { val f = fun(x: Int): Int { return x * 2 } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_anonymous_function_produces_func_ref(self):
        """anonymous_function should produce a function reference CONST."""
        instructions = _parse_kotlin(
            "fun main() { val f = fun(x: Int): Int { return x * 2 } }"
        )
        consts = _find_all(instructions, Opcode.CONST)
        assert any("__anon_fun" in str(inst.operands) for inst in consts)

    def test_anonymous_function_has_params(self):
        """anonymous_function params should produce SYMBOLIC param: entries."""
        instructions = _parse_kotlin(
            "fun main() { val f = fun(x: Int): Int { return x * 2 } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("x" in p for p in param_names)

    def test_anonymous_function_has_return(self):
        """anonymous_function body should produce RETURN."""
        instructions = _parse_kotlin(
            "fun main() { val f = fun(x: Int): Int { return x * 2 } }"
        )
        returns = _find_all(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    def test_anonymous_function_stored_in_var(self):
        """val f = fun(...) should store the function ref in f."""
        instructions = _parse_kotlin(
            "fun main() { val f = fun(x: Int): Int { return x * 2 } }"
        )
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_anonymous_function_no_params(self):
        """fun(): Unit { println(1) } should lower without errors."""
        instructions = _parse_kotlin(
            "fun main() { val f = fun(): Unit { println(1) } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_anonymous_function_multiple_params(self):
        """fun(a: Int, b: Int): Int { return a + b } should handle multiple params."""
        instructions = _parse_kotlin(
            "fun main() { val f = fun(a: Int, b: Int): Int { return a + b } }"
        )
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("a" in p for p in param_names)
        assert any("b" in p for p in param_names)


class TestKotlinUnsignedLiteral:
    def test_unsigned_literal_no_symbolic(self):
        """42u should not produce SYMBOLIC fallthrough."""
        ir = _parse_kotlin("val x = 42u")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsigned_literal" in str(inst.operands) for inst in symbolics)

    def test_unsigned_literal_emits_const(self):
        """Unsigned literal should emit a CONST instruction."""
        ir = _parse_kotlin("val x = 42u")
        consts = _find_all(ir, Opcode.CONST)
        assert len(consts) >= 1

    def test_unsigned_literal_stored(self):
        """Unsigned literal should be stored in a variable."""
        ir = _parse_kotlin("val x = 42u")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestKotlinWildcardImport:
    def test_wildcard_import_no_symbolic(self):
        """import foo.* should not produce SYMBOLIC fallthrough."""
        ir = _parse_kotlin("import kotlin.math.*\nval x = 1")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("wildcard_import" in str(inst.operands) for inst in symbolics)


class TestKotlinCallableReference:
    def test_callable_reference_no_symbolic(self):
        """::println should not produce SYMBOLIC fallthrough."""
        ir = _parse_kotlin("val f = ::println")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("callable_reference" in str(inst.operands) for inst in symbolics)

    def test_callable_reference_emits_load(self):
        """::functionName should emit a LOAD_VAR for the referenced function."""
        ir = _parse_kotlin("val f = ::println")
        loads = _find_all(ir, Opcode.LOAD_VAR)
        assert any("println" in str(inst.operands) for inst in loads)


class TestKotlinSpreadExpression:
    def test_spread_no_symbolic(self):
        """*array should not produce SYMBOLIC fallthrough."""
        ir = _parse_kotlin("""\
val arr = listOf(1, 2, 3)
val x = listOf(*arr)
""")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("spread_expression" in str(inst.operands) for inst in symbolics)


class TestKotlinSetter:
    def test_setter_no_symbolic(self):
        """Property setter should not produce SYMBOLIC."""
        ir = _parse_kotlin("""\
class Foo {
  var x: Int = 0
    set(value) { field = value }
}
val y = 42""")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("setter" in str(inst.operands) for inst in symbolics)

    def test_setter_does_not_block(self):
        """Code after class with setter should be lowered."""
        ir = _parse_kotlin("""\
class Foo {
  var x: Int = 0
    set(value) { field = value }
}
val y = 42""")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("y" in inst.operands for inst in stores)


class TestKotlinBitwiseInfix:
    """Kotlin bitwise infix functions (and, or, xor, shl, shr) emit BINOP."""

    def test_and_emits_binop(self):
        ir = _parse_kotlin("""\
val a = 12
val b = 10
val c = a and b
""")
        binops = _find_all(ir, Opcode.BINOP)
        assert any(
            "&" in inst.operands for inst in binops
        ), "Expected BINOP with '&' for Kotlin 'and' infix"

    def test_xor_emits_binop(self):
        ir = _parse_kotlin("""\
val a = 8
val b = 5
val c = a xor b
""")
        binops = _find_all(ir, Opcode.BINOP)
        assert any(
            "^" in inst.operands for inst in binops
        ), "Expected BINOP with '^' for Kotlin 'xor' infix"

    def test_or_emits_binop(self):
        ir = _parse_kotlin("""\
val a = 12
val b = 10
val c = a or b
""")
        binops = _find_all(ir, Opcode.BINOP)
        assert any(
            "|" in inst.operands for inst in binops
        ), "Expected BINOP with '|' for Kotlin 'or' infix"

    def test_shl_emits_binop(self):
        ir = _parse_kotlin("""\
val a = 1
val c = a shl 3
""")
        binops = _find_all(ir, Opcode.BINOP)
        assert any(
            "<<" in inst.operands for inst in binops
        ), "Expected BINOP with '<<' for Kotlin 'shl' infix"

    def test_shr_emits_binop(self):
        ir = _parse_kotlin("""\
val a = 16
val c = a shr 2
""")
        binops = _find_all(ir, Opcode.BINOP)
        assert any(
            ">>" in inst.operands for inst in binops
        ), "Expected BINOP with '>>' for Kotlin 'shr' infix"

    def test_non_bitwise_infix_emits_call(self):
        """Non-bitwise infix like 'to' should still emit CALL_FUNCTION."""
        ir = _parse_kotlin("""\
val p = 1 to 2
""")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any(
            "to" in str(inst.operands) for inst in calls
        ), "Expected CALL_FUNCTION for non-bitwise 'to' infix"

    def test_bitwise_execution(self):
        """Kotlin bitwise infix produces correct result through VM."""
        vm, stats = execute_for_language(
            "kotlin",
            """\
val a = 12
val b = 10
val c = a and b
val answer = c xor 5
""",
        )
        assert extract_answer(vm, "kotlin") == 13
        assert stats.llm_calls == 0


class TestKotlinInterfaceLowering:
    """Kotlin interface declarations should emit CLASS blocks with method stubs."""

    def test_interface_emits_class_block(self):
        """Interface produces BRANCH-LABEL...LABEL-CONST(<class:>)-STORE_VAR."""
        instructions = _parse_kotlin("interface Drawable { fun draw(): String }")
        consts = _find_all(instructions, Opcode.CONST)
        class_refs = [i for i in consts if "class_" in str(i.operands)]
        assert len(class_refs) == 1
        assert "Drawable" in str(class_refs[0].operands[0])
        labels = _find_all(instructions, Opcode.LABEL)
        assert any("class_Drawable" in (i.label or "") for i in labels)

    def test_interface_methods_emit_function_labels(self):
        """Each interface method should produce a FUNC_DEF label."""
        instructions = _parse_kotlin(
            "interface Shape { fun area(): Double\n fun perimeter(): Double }"
        )
        labels = _find_all(instructions, Opcode.LABEL)
        func_labels = [i for i in labels if "func_" in (i.label or "")]
        func_label_names = [i.label for i in func_labels]
        assert any("area" in lbl for lbl in func_label_names)
        assert any("perimeter" in lbl for lbl in func_label_names)

    def test_interface_methods_seed_return_types(self):
        """Interface method return types are seeded in type_env_builder."""
        _instructions, builder = _parse_kotlin_with_types(
            "interface Calculator { fun compute(x: Int): Int\n fun reset(): Boolean }"
        )
        rt = dict(builder.func_return_types)
        compute_entries = {k: v for k, v in rt.items() if "compute" in k}
        reset_entries = {k: v for k, v in rt.items() if "reset" in k}
        assert (
            len(compute_entries) >= 1
        ), f"Expected return type for 'compute', got: {rt}"
        assert len(reset_entries) >= 1, f"Expected return type for 'reset', got: {rt}"

    def test_interface_methods_inject_this(self):
        """Interface methods should have 'this' parameter injection."""
        instructions = _parse_kotlin("interface Greeter { fun greet(): String }")
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        this_params = [i for i in symbolics if "param:this" in str(i.operands)]
        assert len(this_params) >= 1, "Interface methods should inject 'this'"


class TestKotlinPrimaryConstructor:
    """Primary constructor val params must generate __init__ with STORE_FIELD."""

    def test_primary_constructor_generates_init(self):
        ir = _parse_kotlin("class Node(val value: Int, val nextNode: Node?)")
        func_refs = [
            i
            for i in _find_all(ir, Opcode.CONST)
            if i.operands and "__init__" in str(i.operands[0])
        ]
        assert len(func_refs) == 1, f"Expected one __init__ FUNC_REF, got {func_refs}"

    def test_primary_constructor_stores_fields(self):
        ir = _parse_kotlin("class Node(val value: Int, val nextNode: Node?)")
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [sf.operands[1] for sf in store_fields]
        assert (
            "value" in field_names
        ), f"Expected STORE_FIELD for 'value', got {field_names}"
        assert (
            "nextNode" in field_names
        ), f"Expected STORE_FIELD for 'nextNode', got {field_names}"

    def test_primary_constructor_declares_params(self):
        ir = _parse_kotlin("class Node(val value: Int, val nextNode: Node?)")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_names = [
            s.operands[0] for s in symbolics if s.operands[0].startswith("param:")
        ]
        assert "param:value" in param_names
        assert "param:nextNode" in param_names

    def test_class_without_primary_constructor_no_init(self):
        ir = _parse_kotlin("class Empty")
        func_refs = [
            i
            for i in _find_all(ir, Opcode.CONST)
            if i.operands and "__init__" in str(i.operands[0])
        ]
        assert (
            len(func_refs) == 0
        ), "Class without primary constructor should not generate __init__"


class TestKotlinSecondaryConstructor:
    """Secondary constructors emit __init__ with delegation and body."""

    def test_secondary_constructor_generates_init(self):
        """Secondary constructor should produce an __init__ FUNC_REF."""
        ir = _parse_kotlin("""\
class Rect(val w: Int, val h: Int) {
    constructor(side: Int) : this(side, side)
}
""")
        func_ref_instrs = [
            i
            for i in _find_all(ir, Opcode.CONST)
            if i.operands and "__init__" in str(i.operands[0])
        ]
        # primary + secondary = 2 __init__ refs
        assert (
            len(func_ref_instrs) == 2
        ), f"Expected 2 __init__ CONST refs (primary + secondary), got {func_ref_instrs}"

    def test_secondary_constructor_has_params(self):
        """Secondary constructor should emit SYMBOLIC param: for its parameters."""
        ir = _parse_kotlin("""\
class Rect(val w: Int, val h: Int) {
    constructor(side: Int) : this(side, side)
}
""")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_names = [
            s.operands[0] for s in symbolics if s.operands[0].startswith("param:")
        ]
        assert "param:side" in param_names, f"Expected param:side, got {param_names}"

    def test_secondary_constructor_delegation_stores_fields(self):
        """this(...) delegation should emit STORE_FIELD for primary params."""
        ir = _parse_kotlin("""\
class Rect(val w: Int, val h: Int) {
    constructor(side: Int) : this(side, side)
}
""")
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [sf.operands[1] for sf in store_fields]
        # Primary constructor stores w, h; secondary also stores w, h via delegation
        assert (
            field_names.count("w") == 2
        ), f"Expected 2 STORE_FIELD for 'w', got {field_names}"
        assert (
            field_names.count("h") == 2
        ), f"Expected 2 STORE_FIELD for 'h', got {field_names}"

    def test_secondary_constructor_no_symbolic_unsupported(self):
        """Secondary constructor should not produce SYMBOLIC unsupported."""
        ir = _parse_kotlin("""\
class Rect(val w: Int, val h: Int) {
    constructor(side: Int) : this(side, side)
}
""")
        unsupported = [
            i
            for i in _find_all(ir, Opcode.SYMBOLIC)
            if "unsupported" in str(i.operands)
        ]
        assert (
            unsupported == []
        ), f"Should not have unsupported symbolics: {unsupported}"


class TestKotlinPropertyAccessors:
    """Tests for custom property getter/setter IR emission."""

    def test_getter_emits_synthetic_method(self):
        """Property getter should emit a __get_x__ method label."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        get() = field + 1
}""")
        labels = _find_all(ir, Opcode.LABEL)
        getter_labels = [
            inst for inst in labels if inst.label and "__get_x__" in inst.label
        ]
        assert len(getter_labels) >= 1, "Expected a __get_x__ method label"

    def test_setter_emits_synthetic_method(self):
        """Property setter should emit a __set_x__ method label."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        set(value) { field = value * 2 }
}""")
        labels = _find_all(ir, Opcode.LABEL)
        setter_labels = [
            inst for inst in labels if inst.label and "__set_x__" in inst.label
        ]
        assert len(setter_labels) >= 1, "Expected a __set_x__ method label"

    def test_getter_setter_both_emitted(self):
        """Both getter and setter should produce synthetic methods."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        get() = field + 1
        set(value) { field = value * 2 }
}""")
        labels = _find_all(ir, Opcode.LABEL)
        label_names = [inst.label for inst in labels if inst.label]
        assert any("__get_x__" in lbl for lbl in label_names)
        assert any("__set_x__" in lbl for lbl in label_names)

    def test_property_without_accessors_unchanged(self):
        """Property without custom accessors should not emit synthetic methods."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
}""")
        labels = _find_all(ir, Opcode.LABEL)
        label_names = [inst.label for inst in labels if inst.label]
        assert not any("__get_" in lbl for lbl in label_names)
        assert not any("__set_" in lbl for lbl in label_names)

    def test_field_keyword_in_getter_emits_load_field(self):
        """'field' in getter body should emit LOAD_FIELD this 'x'."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        get() = field
}""")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any(
            "x" in inst.operands for inst in load_fields
        ), f"Expected LOAD_FIELD with field 'x', got: {[(inst.operands) for inst in load_fields]}"

    def test_this_dot_x_with_getter_emits_call_method(self):
        """this.x with custom getter should emit CALL_METHOD __get_x__."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        get() = field + 1
    fun bar(): Int {
        return this.x
    }
}""")
        call_methods = _find_all(ir, Opcode.CALL_METHOD)
        assert any(
            "__get_x__" in inst.operands for inst in call_methods
        ), f"Expected CALL_METHOD with __get_x__, got: {[(inst.operands) for inst in call_methods]}"

    def test_field_keyword_in_setter_emits_store_field(self):
        """'field = value' in setter body should emit STORE_FIELD this 'x'."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        set(value) { field = value }
}""")
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any(
            "x" in inst.operands for inst in store_fields
        ), f"Expected STORE_FIELD with field 'x', got: {[(inst.operands) for inst in store_fields]}"

    def test_this_dot_x_assign_with_setter_emits_call_method(self):
        """this.x = val with custom setter should emit CALL_METHOD __set_x__."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        set(value) { field = value * 2 }
    fun bar() {
        this.x = 5
    }
}""")
        call_methods = _find_all(ir, Opcode.CALL_METHOD)
        assert any(
            "__set_x__" in inst.operands for inst in call_methods
        ), f"Expected CALL_METHOD with __set_x__, got: {[(inst.operands) for inst in call_methods]}"


class TestKotlinUnsignedLiteral:
    def test_unsigned_int_suffix_stripped(self):
        """val x = 42u should emit CONST '42', not '42u'."""
        ir = _parse_kotlin("val x = 42u")
        consts = _find_all(ir, Opcode.CONST)
        const_values = [inst.operands[0] for inst in consts]
        assert "42" in const_values
        assert "42u" not in const_values

    def test_unsigned_long_suffix_stripped(self):
        """val x = 42UL should emit CONST '42', not '42UL'."""
        ir = _parse_kotlin("val x = 42UL")
        consts = _find_all(ir, Opcode.CONST)
        const_values = [inst.operands[0] for inst in consts]
        assert "42" in const_values
        assert "42UL" not in const_values

    def test_unsigned_lowercase_suffix(self):
        """val x = 100uL should strip mixed-case suffix."""
        ir = _parse_kotlin("val x = 100uL")
        consts = _find_all(ir, Opcode.CONST)
        const_values = [inst.operands[0] for inst in consts]
        assert "100" in const_values

    def test_unsigned_hex_literal(self):
        """val x = 0xFFu should emit '0xFF', not '0xFFu'."""
        ir = _parse_kotlin("val x = 0xFFu")
        consts = _find_all(ir, Opcode.CONST)
        const_values = [inst.operands[0] for inst in consts]
        assert "0xFF" in const_values
