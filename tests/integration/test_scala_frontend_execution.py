"""Integration tests for Scala frontend: export_declaration, val_declaration, alternative_pattern, array indexing."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_scala(source: str, max_steps: int = 200):
    vm = run(source, language=Language.SCALA, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


def _run_scala_vm(source: str, max_steps: int = 200):
    """Return full VM for heap inspection."""
    return run(source, language=Language.SCALA, max_steps=max_steps)


class TestScalaExportDeclarationExecution:
    def test_export_does_not_crash(self):
        """export declaration should execute without errors."""
        locals_ = _run_scala("export foo._\nval x = 42")
        assert locals_["x"] == 42


class TestScalaValDeclarationExecution:
    def test_code_after_val_decl_executes(self):
        """Code after abstract val declaration should execute."""
        locals_ = _run_scala("val y = 42")
        assert locals_["y"] == 42


class TestScalaAlternativePatternExecution:
    def test_alternative_pattern_match(self):
        """match with alternative pattern should execute."""
        locals_ = _run_scala("""\
val x = 1
val r = x match {
  case 1 | 2 => 10
  case _ => 0
}""")
        assert locals_["r"] == 10

    def test_alternative_pattern_no_match(self):
        """match with non-matching alternative should fall through to default."""
        locals_ = _run_scala("""\
val x = 5
val r = x match {
  case 1 | 2 => 10
  case _ => 0
}""")
        assert locals_["r"] == 0


class TestScalaPrimaryConstructorExecution:
    """Primary constructor val params produce concrete field values after new."""

    def test_field_access_on_constructed_object(self):
        """new with primary constructor val params should store and
        retrieve field values concretely."""
        locals_ = _run_scala(
            """\
object M {
    class Box(val x: Int)
    val b = new Box(42)
    val answer = b.x
}""",
            max_steps=500,
        )
        assert locals_["answer"] == 42

    def test_linked_list_field_traversal(self):
        """Linked list built with new + primary constructor should
        allow recursive traversal to produce concrete sum."""
        locals_ = _run_scala(
            """\
object M {
    class Node(val value: Int, val nextNode: Node)

    def sumList(node: Node, count: Int): Int = {
        if (count <= 0) {
            return 0
        }
        return node.value + sumList(node.nextNode, count - 1)
    }

    val n3 = new Node(3, null)
    val n2 = new Node(2, n3)
    val n1 = new Node(1, n2)
    val answer = sumList(n1, 3)
}""",
            max_steps=1000,
        )
        assert locals_["answer"] == 6


class TestScalaArrayIndexingExecution:
    """Scala arr(i) syntax should resolve to array indexing at runtime."""

    def test_basic_array_indexing(self):
        """arr(0), arr(1), arr(2) should return correct elements."""
        locals_ = _run_scala("""\
val arr = Array(10, 20, 30)
val a = arr(0)
val b = arr(1)
val c = arr(2)""")
        assert locals_["a"] == 10
        assert locals_["b"] == 20
        assert locals_["c"] == 30

    def test_variable_index(self):
        """arr(i) with variable i should return the correct element."""
        locals_ = _run_scala("""\
val arr = Array(10, 20, 30)
var i = 1
val x = arr(i)""")
        assert locals_["x"] == 20

    def test_expression_index(self):
        """arr(i + 1) should evaluate the index expression."""
        locals_ = _run_scala("""\
val arr = Array(10, 20, 30)
var i = 0
val x = arr(i + 1)""")
        assert locals_["x"] == 20

    def test_array_write_and_read(self):
        """arr(0) = 99; arr(0) should return 99."""
        vm = _run_scala_vm("""\
var arr = Array(10, 20, 30)
arr(0) = 99
val x = arr(0)""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["x"] == 99

    def test_swap_elements(self):
        """Swap arr(0) and arr(1) via temp variable."""
        vm = _run_scala_vm(
            """\
var arr = Array(30, 10, 20)
val temp = arr(0)
arr(0) = arr(1)
arr(1) = temp
val a = arr(0)
val b = arr(1)""",
            max_steps=300,
        )
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["a"] == 10
        assert locals_["b"] == 30

    def test_string_character_indexing(self):
        """s(1) on a string should return the character at index 1."""
        locals_ = _run_scala("""\
val s = "hello"
val c = s(1)""")
        assert locals_["c"] == "e"
