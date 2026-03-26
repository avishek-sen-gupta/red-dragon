"""Integration tests for Kotlin frontend: unsigned_literal, callable_reference, spread_expression, setter."""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.refs.func_ref import BoundFuncRef
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run_kotlin(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.KOTLIN, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestKotlinUnsignedLiteralExecution:
    def test_unsigned_literal_assigned(self):
        """val x = 42u should execute and store 42."""
        vars_ = _run_kotlin("val x = 42u")
        assert vars_[VarName("x")] == 42

    def test_unsigned_literal_in_arithmetic(self):
        """Unsigned literal should be usable in arithmetic."""
        vars_ = _run_kotlin("""\
val x = 10u
val z = x + 1
""")
        assert vars_[VarName("z")] == 11

    def test_unsigned_long_literal(self):
        """val x = 42UL should store 42."""
        vars_ = _run_kotlin("val x = 42UL")
        assert vars_[VarName("x")] == 42


class TestKotlinCallableReferenceExecution:
    def test_callable_reference_assigned(self):
        """val f = ::someFunc should store a BoundFuncRef."""
        vars_ = _run_kotlin("""\
fun double(x: Int): Int { return x * 2 }
val f = ::double
""")
        assert isinstance(vars_[VarName("f")], BoundFuncRef)
        assert vars_[VarName("f")].func_ref.name == "double"

    def test_callable_reference_does_not_block_execution(self):
        """Callable reference should not prevent subsequent code from executing."""
        vars_ = _run_kotlin("""\
fun double(x: Int): Int { return x * 2 }
val f = ::double
val y = 42
""")
        assert vars_[VarName("y")] == 42


class TestKotlinSpreadExpressionExecution:
    def test_spread_does_not_crash(self):
        """Spread operator (*) in function call should produce correct result."""
        vars_ = _run_kotlin("""\
fun sum(a: Int, b: Int, c: Int): Int { return a + b + c }
val arr = intArrayOf(1, 2, 3)
val answer = sum(*arr)
""")
        assert vars_[VarName("answer")] == 6


class TestKotlinSetterExecution:
    def test_code_after_class_with_setter_executes(self):
        """Code after class with property setter should execute."""
        locals_ = _run_kotlin("""\
class Foo {
  var x: Int = 0
    set(value) { field = value }
}
val y = 42""")
        assert locals_[VarName("y")] == 42


class TestKotlinPrimaryConstructorExecution:
    """Primary constructor with val params produces concrete field values."""

    def test_field_access_on_constructed_object(self):
        """Constructing a class with primary constructor val params
        and accessing fields should return concrete values."""
        vars_ = _run_kotlin("""\
class Box(val x: Int)
val b = Box(42)
val answer = b.x
""")
        assert vars_[VarName("answer")] == 42

    def test_linked_list_field_traversal(self):
        """Linked list built with primary constructor should allow
        field traversal to produce concrete sum."""
        vars_ = _run_kotlin(
            """\
class Node(val value: Int, val nextNode: Node?)

fun sumList(node: Node, count: Int): Int {
    if (count <= 0) {
        return 0
    }
    return node.value + sumList(node.nextNode!!, count - 1)
}

val n3 = Node(3, null)
val n2 = Node(2, n3)
val n1 = Node(1, n2)
val answer = sumList(n1, 3)
""",
            max_steps=1000,
        )
        assert vars_[VarName("answer")] == 6


class TestKotlinSecondaryConstructorExecution:
    """Secondary constructors with this() delegation execute correctly."""

    def test_secondary_constructor_delegates_to_primary(self):
        """constructor(side) : this(side, side) should create object with both fields."""
        vars_ = _run_kotlin("""\
class Rect(val w: Int, val h: Int) {
    constructor(side: Int) : this(side, side)
}
val r = Rect(5)
val answer = r.w
""")
        assert vars_[VarName("answer")] == 5

    def test_secondary_constructor_with_body(self):
        """Secondary constructor body should execute after delegation."""
        vars_ = _run_kotlin(
            """\
class Pair(val a: Int, val b: Int) {
    constructor(x: Int) : this(x, x + 1) {
        val sum = x + x + 1
    }
}
val p = Pair(3)
val answer = p.b
""",
            max_steps=1000,
        )
        assert vars_[VarName("answer")] == 4

    def test_zero_arg_secondary_constructor(self):
        """constructor() : this(default) should work with no args."""
        vars_ = _run_kotlin("""\
class Box(val x: Int) {
    constructor() : this(99)
}
val b = Box()
val answer = b.x
""")
        assert vars_[VarName("answer")] == 99


class TestKotlinImplicitThisFieldExecution:
    """Bare field names in method/constructor bodies resolve via implicit this."""

    def test_method_reads_field_by_bare_name(self):
        """this.value accessed as bare 'value' in method body."""
        vars_ = _run_kotlin("""\
class Box(val value: Int) {
    fun get(): Int {
        return value
    }
}
val b = Box(42)
val answer = b.get()
""")
        assert vars_[VarName("answer")] == 42

    def test_secondary_constructor_body_reads_field(self):
        """Field set by delegation readable by bare name in constructor body."""
        vars_ = _run_kotlin(
            """\
class Counter(val count: Int) {
    var doubled: Int = 0
    constructor(x: Int, scale: Int) : this(x) {
        doubled = count * scale
    }
}
val c = Counter(3, 2)
val answer = c.doubled
""",
            max_steps=1000,
        )
        assert vars_[VarName("answer")] == 6


class TestKotlinPropertyAccessorExecution:
    """Integration tests for custom property getter/setter execution."""

    def test_getter_transforms_read(self):
        """Custom getter should transform the read value."""
        vars_ = _run_kotlin(
            """\
class Foo {
    var x: Int = 10
        get() = field + 1
    fun getX(): Int {
        return this.x
    }
}
val foo = Foo()
val result = foo.getX()""",
            max_steps=1000,
        )
        assert vars_[VarName("result")] == 11

    def test_setter_transforms_write(self):
        """Custom setter should transform the written value."""
        vars_ = _run_kotlin(
            """\
class Foo {
    var x: Int = 0
        set(value) { field = value * 2 }
    fun setX(v: Int) {
        this.x = v
    }
    fun getX(): Int {
        return this.x
    }
}
val foo = Foo()
foo.setX(5)
val result = foo.getX()""",
            max_steps=1500,
        )
        assert vars_[VarName("result")] == 10

    def test_getter_and_setter_together(self):
        """Both getter and setter should apply their transformations."""
        vars_ = _run_kotlin(
            """\
class Foo {
    var x: Int = 0
        get() = field + 1
        set(value) { field = value * 2 }
    fun setX(v: Int) {
        this.x = v
    }
    fun getX(): Int {
        return this.x
    }
}
val foo = Foo()
foo.setX(5)
val result = foo.getX()""",
            max_steps=1500,
        )
        # setter stores 5 * 2 = 10, getter returns 10 + 1 = 11
        assert vars_[VarName("result")] == 11

    def test_property_without_accessors_regression(self):
        """Property without custom accessors should still work as plain field."""
        vars_ = _run_kotlin(
            """\
class Foo {
    var x: Int = 42
    fun getX(): Int {
        return this.x
    }
}
val foo = Foo()
val result = foo.getX()""",
            max_steps=1000,
        )
        assert vars_[VarName("result")] == 42
