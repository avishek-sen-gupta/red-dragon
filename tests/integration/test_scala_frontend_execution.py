"""Integration tests for Scala frontend: export_declaration, val_declaration, alternative_pattern, array indexing."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run_scala(source: str, max_steps: int = 200):
    vm = run(
        source,
        language=Language.SCALA,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


def _run_scala_vm(source: str, max_steps: int = 200):
    """Return full VM for heap inspection."""
    return run(source, language=Language.SCALA, max_steps=max_steps)


class TestScalaExportDeclarationExecution:
    def test_export_does_not_crash(self):
        """export declaration should execute without errors."""
        locals_ = _run_scala("export foo._\nval x = 42")
        assert locals_[VarName("x")] == 42


class TestScalaValDeclarationExecution:
    def test_code_after_val_decl_executes(self):
        """Code after abstract val declaration should execute."""
        locals_ = _run_scala("val y = 42")
        assert locals_[VarName("y")] == 42


class TestScalaAlternativePatternExecution:
    def test_alternative_pattern_match(self):
        """match with alternative pattern should execute."""
        locals_ = _run_scala("""\
val x = 1
val r = x match {
  case 1 | 2 => 10
  case _ => 0
}""")
        assert locals_[VarName("r")] == 10

    def test_alternative_pattern_no_match(self):
        """match with non-matching alternative should fall through to default."""
        locals_ = _run_scala("""\
val x = 5
val r = x match {
  case 1 | 2 => 10
  case _ => 0
}""")
        assert locals_[VarName("r")] == 0


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
        assert locals_[VarName("answer")] == 42

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
        assert locals_[VarName("answer")] == 6


class TestScalaArrayIndexingExecution:
    """Scala arr(i) syntax should resolve to array indexing at runtime."""

    def test_basic_array_indexing(self):
        """arr(0), arr(1), arr(2) should return correct elements."""
        locals_ = _run_scala("""\
val arr = Array(10, 20, 30)
val a = arr(0)
val b = arr(1)
val c = arr(2)""")
        assert locals_[VarName("a")] == 10
        assert locals_[VarName("b")] == 20
        assert locals_[VarName("c")] == 30

    def test_variable_index(self):
        """arr(i) with variable i should return the correct element."""
        locals_ = _run_scala("""\
val arr = Array(10, 20, 30)
var i = 1
val x = arr(i)""")
        assert locals_[VarName("x")] == 20

    def test_expression_index(self):
        """arr(i + 1) should evaluate the index expression."""
        locals_ = _run_scala("""\
val arr = Array(10, 20, 30)
var i = 0
val x = arr(i + 1)""")
        assert locals_[VarName("x")] == 20

    def test_array_write_and_read(self):
        """arr(0) = 99; arr(0) should return 99."""
        vm = _run_scala_vm("""\
var arr = Array(10, 20, 30)
arr(0) = 99
val x = arr(0)""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_[VarName("x")] == 99

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
        assert locals_[VarName("a")] == 10
        assert locals_[VarName("b")] == 30

    def test_string_character_indexing(self):
        """s(1) on a string should return the character at index 1."""
        locals_ = _run_scala("""\
val s = "hello"
val c = s(1)""")
        assert locals_[VarName("c")] == "e"


class TestScalaAuxiliaryConstructorExecution:
    """Scala def this(...) = this(args) auxiliary constructor chaining."""

    def test_single_field_auxiliary_constructor(self):
        """Two-arg auxiliary constructor delegates to primary via this(v + scale)."""
        locals_ = _run_scala(
            """\
class Box(val value: Int) {
  def this(v: Int, scale: Int) = this(v + scale)
}
val b = new Box(3, 4)
val answer = b.value
""",
            max_steps=1000,
        )
        assert locals_[VarName("answer")] == 7

    def test_auxiliary_with_field_initializer(self):
        """Field initializer should exist after auxiliary constructor chaining."""
        locals_ = _run_scala(
            """\
class Calc(val result: Int) {
  val extra: Int = 10
  def this(a: Int, b: Int) = this(a + b)
  def total(): Int = result + extra
}
val c = new Calc(3, 4)
val answer = c.total()
""",
            max_steps=1000,
        )
        assert locals_[VarName("answer")] == 17

    def test_auxiliary_body_reads_field_by_bare_name(self):
        """After this(...) delegation, body can read fields via implicit this."""
        locals_ = _run_scala(
            """\
class Counter(val count: Int) {
  var doubled: Int = 0
  def this(c: Int, scale: Int) = {
    this(c)
    doubled = count * scale
  }
}
val obj = new Counter(5, 3)
val answer = obj.doubled
""",
            max_steps=1000,
        )
        assert locals_[VarName("answer")] == 15


class TestScalaEnumExecution:
    def test_simple_enum_field_access(self):
        """enum Color { case Red, Green, Blue }; Color.Red should resolve."""
        locals_ = _run_scala("""\
enum Color {
  case Red, Green, Blue
}
val c = Color.Red
""")
        assert locals_[VarName("c")] == "Red"

    def test_enum_all_variants_accessible(self):
        """All enum variants should be accessible via dot notation."""
        locals_ = _run_scala("""\
enum Direction {
  case North, South, East, West
}
val n = Direction.North
val s = Direction.South
val e = Direction.East
val w = Direction.West
""")
        assert locals_[VarName("n")] == "North"
        assert locals_[VarName("s")] == "South"
        assert locals_[VarName("e")] == "East"
        assert locals_[VarName("w")] == "West"

    def test_enum_variant_equality(self):
        """Two accesses to the same enum variant should be equal."""
        locals_ = _run_scala("""\
enum Color {
  case Red, Green, Blue
}
val a = Color.Red
val b = Color.Red
val same = a == b
""")
        assert locals_[VarName("same")] is True

    def test_enum_match_expression(self):
        """Match on enum values using pattern matching."""
        locals_ = _run_scala(
            """\
enum Color {
  case Red, Green, Blue
}
val c = Color.Green
val r = c match {
  case Color.Red => 1
  case Color.Green => 2
  case Color.Blue => 3
}
""",
            max_steps=500,
        )
        assert locals_[VarName("r")] == 2

    def test_enum_equality_comparison(self):
        """Enum values can be compared with == in if expressions."""
        locals_ = _run_scala(
            """\
enum Direction {
  case North, South, East, West
}
val d = Direction.North
val r = if (d == Direction.North) 1 else 0
""",
            max_steps=500,
        )
        assert locals_[VarName("r")] == 1

    def test_enum_as_function_argument(self):
        """Enum values can be passed to functions and matched inside."""
        locals_ = _run_scala(
            """\
enum Color {
  case Red, Green, Blue
}
def colorToInt(c: Int): Int = c match {
  case Color.Red => 1
  case Color.Green => 2
  case Color.Blue => 3
  case _ => 0
}
val result = colorToInt(Color.Green)
""",
            max_steps=500,
        )
        assert locals_[VarName("result")] == 2

    def test_enum_match_wildcard_fallback(self):
        """Enum match with wildcard catches unmatched variants."""
        locals_ = _run_scala(
            """\
enum Color {
  case Red, Green, Blue
}
val c = Color.Blue
val r = c match {
  case Color.Red => 1
  case _ => 99
}
""",
            max_steps=500,
        )
        assert locals_[VarName("r")] == 99
