"""Integration tests for C++ overload resolution through full pipeline.

Tests that when C++ source code defines overloaded methods, the executor picks
the correct overload based on call-site argument arity and types.
"""

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap, unwrap_locals


class TestCppOverloadResolutionByArity:
    """C++ methods overloaded by parameter count."""

    def test_unary_vs_binary_picks_unary(self):
        source = """\
class Calc {
public:
    int add(int a) { return a; }
    int add(int a, int b) { return a + b; }
};
Calc c;
int x = c.add(5);
"""
        vm = run(source, language=Language.CPP, max_steps=2000)
        lv = unwrap_locals(vm.call_stack[0].local_vars)
        assert lv[VarName("x")] == 5

    def test_unary_vs_binary_picks_binary(self):
        source = """\
class Calc {
public:
    int add(int a) { return a; }
    int add(int a, int b) { return a + b; }
};
Calc c;
int y = c.add(3, 4);
"""
        vm = run(source, language=Language.CPP, max_steps=2000)
        lv = unwrap_locals(vm.call_stack[0].local_vars)
        assert lv[VarName("y")] == 7

    def test_three_arity_overloads(self):
        source = """\
class Calc {
public:
    int add(int a) { return a; }
    int add(int a, int b) { return a + b; }
    int add(int a, int b, int c) { return a + b + c; }
};
Calc c;
int r1 = c.add(5);
int r2 = c.add(3, 4);
int r3 = c.add(1, 2, 3);
"""
        vm = run(source, language=Language.CPP, max_steps=2000)
        lv = unwrap_locals(vm.call_stack[0].local_vars)
        assert lv[VarName("r1")] == 5
        assert lv[VarName("r2")] == 7
        assert lv[VarName("r3")] == 6


class TestCppOverloadResolutionByType:
    """C++ methods overloaded by parameter type (same arity)."""

    def test_int_vs_string_picks_int(self):
        source = """\
class Printer {
public:
    int show(int x) { return x + 1; }
    std::string show(std::string s) { return "str:" + s; }
};
Printer p;
int result = p.show(42);
"""
        vm = run(source, language=Language.CPP, max_steps=2000)
        lv = unwrap_locals(vm.call_stack[0].local_vars)
        assert lv[VarName("result")] == 43

    def test_int_vs_string_picks_string(self):
        source = """\
class Printer {
public:
    std::string show(int x) { return "int:" + x; }
    std::string show(std::string s) { return "str:" + s; }
};
Printer p;
std::string result = p.show("hello");
"""
        vm = run(source, language=Language.CPP, max_steps=2000)
        lv = unwrap_locals(vm.call_stack[0].local_vars)
        assert lv[VarName("result")] == "str:hello"
