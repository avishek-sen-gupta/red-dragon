"""Integration tests for Scala frontend: export_declaration, val_declaration, alternative_pattern."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_scala(source: str, max_steps: int = 200):
    vm = run(source, language=Language.SCALA, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


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
