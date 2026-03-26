"""Integration tests for Kotlin overload resolution through full pipeline.

Tests that when Kotlin source code defines overloaded methods, the executor picks
the correct overload based on call-site argument arity and types.
"""

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap


class TestKotlinOverloadResolutionByArity:
    """Kotlin methods overloaded by parameter count."""

    def test_unary_vs_binary_picks_unary(self):
        source = """\
class Calc {
    fun add(a: Int): Int { return a }
    fun add(a: Int, b: Int): Int { return a + b }
}
val c = Calc()
val x = c.add(5)
"""
        vm = run(source, language=Language.KOTLIN, max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get(VarName("x"))) == 5

    def test_unary_vs_binary_picks_binary(self):
        source = """\
class Calc {
    fun add(a: Int): Int { return a }
    fun add(a: Int, b: Int): Int { return a + b }
}
val c = Calc()
val y = c.add(3, 4)
"""
        vm = run(source, language=Language.KOTLIN, max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get(VarName("y"))) == 7

    def test_three_arity_overloads(self):
        source = """\
class Calc {
    fun add(a: Int): Int { return a }
    fun add(a: Int, b: Int): Int { return a + b }
    fun add(a: Int, b: Int, c: Int): Int { return a + b + c }
}
val c = Calc()
val r1 = c.add(5)
val r2 = c.add(3, 4)
val r3 = c.add(1, 2, 3)
"""
        vm = run(source, language=Language.KOTLIN, max_steps=2000)
        lv = vm.call_stack[0].local_vars
        assert unwrap(lv.get("r1")) == 5
        assert unwrap(lv.get("r2")) == 7
        assert unwrap(lv.get("r3")) == 6


class TestKotlinOverloadResolutionByType:
    """Kotlin methods overloaded by parameter type (same arity)."""

    def test_int_vs_string_picks_int(self):
        source = """\
class Printer {
    fun show(x: Int): Int { return x + 1 }
    fun show(s: String): String { return "str:" + s }
}
val p = Printer()
val result = p.show(42)
"""
        vm = run(source, language=Language.KOTLIN, max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get(VarName("result"))) == 43

    def test_int_vs_string_picks_string(self):
        source = """\
class Printer {
    fun show(x: Int): String { return "int:" + x }
    fun show(s: String): String { return "str:" + s }
}
val p = Printer()
val result = p.show("hello")
"""
        vm = run(source, language=Language.KOTLIN, max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get(VarName("result"))) == "str:hello"
