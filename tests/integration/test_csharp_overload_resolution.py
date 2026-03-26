"""Integration tests for C# overload resolution through full pipeline.

Tests that when C# source code defines overloaded methods, the executor picks
the correct overload based on call-site argument arity and types.
"""

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap


class TestCSharpOverloadResolutionByArity:
    """C# methods overloaded by parameter count."""

    def test_unary_vs_binary_picks_unary(self):
        source = """\
class Calc {
    int Add(int a) { return a; }
    int Add(int a, int b) { return a + b; }
}
Calc c = new Calc();
int x = c.Add(5);
"""
        vm = run(source, language=Language.CSHARP, max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get(VarName("x"))) == 5

    def test_unary_vs_binary_picks_binary(self):
        source = """\
class Calc {
    int Add(int a) { return a; }
    int Add(int a, int b) { return a + b; }
}
Calc c = new Calc();
int y = c.Add(3, 4);
"""
        vm = run(source, language=Language.CSHARP, max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get(VarName("y"))) == 7

    def test_three_arity_overloads(self):
        source = """\
class Calc {
    int Add(int a) { return a; }
    int Add(int a, int b) { return a + b; }
    int Add(int a, int b, int c) { return a + b + c; }
}
Calc c = new Calc();
int r1 = c.Add(5);
int r2 = c.Add(3, 4);
int r3 = c.Add(1, 2, 3);
"""
        vm = run(source, language=Language.CSHARP, max_steps=2000)
        lv = vm.call_stack[0].local_vars
        assert unwrap(lv.get("r1")) == 5
        assert unwrap(lv.get("r2")) == 7
        assert unwrap(lv.get("r3")) == 6


class TestCSharpOverloadResolutionByType:
    """C# methods overloaded by parameter type (same arity)."""

    def test_int_vs_string_picks_int(self):
        source = """\
class Printer {
    int Show(int x) {
        return x + 1;
    }
    string Show(string s) {
        return "str:" + s;
    }
}
Printer p = new Printer();
int result = p.Show(42);
"""
        vm = run(source, language=Language.CSHARP, max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get(VarName("result"))) == 43

    def test_int_vs_string_picks_string(self):
        source = """\
class Printer {
    string Show(int x) {
        return "int:" + x;
    }
    string Show(string s) {
        return "str:" + s;
    }
}
Printer p = new Printer();
string result = p.Show("hello");
"""
        vm = run(source, language=Language.CSHARP, max_steps=2000)
        assert unwrap(vm.call_stack[0].local_vars.get(VarName("result"))) == "str:hello"
