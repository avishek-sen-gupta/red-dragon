"""Tests for closure support — capturing enclosing scope variables."""

from __future__ import annotations

from interpreter.run import run


def _run_program(source: str, max_steps: int = 200) -> dict:
    """Run a program and return the main frame's local_vars."""
    vm = run(source, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestSimpleClosure:
    def test_make_adder(self):
        source = """\
def make_adder(x):
    def adder(y):
        return x + y
    return adder

add5 = make_adder(5)
result = add5(3)
"""
        vars_ = _run_program(source)
        assert vars_["result"] == 8

    def test_captured_var_not_in_caller_scope(self):
        """The closure should carry 'x' even though caller has no 'x'."""
        source = """\
def make_adder(x):
    def adder(y):
        return x + y
    return adder

f = make_adder(10)
result = f(7)
"""
        vars_ = _run_program(source)
        assert vars_["result"] == 17


class TestMultipleClosures:
    def test_different_captures_from_same_factory(self):
        """Two closures from the same factory should have independent captures."""
        source = """\
def make_multiplier(factor):
    def multiply(x):
        return x * factor
    return multiply

double = make_multiplier(2)
triple = make_multiplier(3)
a = double(5)
b = triple(5)
"""
        vars_ = _run_program(source)
        assert vars_["a"] == 10
        assert vars_["b"] == 15

    def test_closures_do_not_interfere(self):
        source = """\
def make_greeter(prefix):
    def greet(name):
        return prefix + name
    return greet

hello = make_greeter("Hello ")
bye = make_greeter("Bye ")
a = hello("Alice")
b = bye("Bob")
"""
        vars_ = _run_program(source)
        assert vars_["a"] == "Hello Alice"
        assert vars_["b"] == "Bye Bob"


class TestClosureWithMultipleVars:
    def test_captures_all_enclosing_vars(self):
        source = """\
def make_linear(m, b):
    def f(x):
        return m * x + b
    return f

line = make_linear(3, 7)
result = line(10)
"""
        vars_ = _run_program(source)
        assert vars_["result"] == 37  # 3*10 + 7


class TestNonClosureFunctionsUnaffected:
    def test_top_level_function_no_closure(self):
        """Top-level functions should not create closure entries."""
        source = """\
def add(a, b):
    return a + b

result = add(3, 4)
"""
        vm = run(source, max_steps=100)
        assert vm.call_stack[0].local_vars["result"] == 7
        assert len(vm.closures) == 0

    def test_factorial_unchanged(self):
        source = """\
def factorial(n):
    if n <= 1:
        return 1
    else:
        return n * factorial(n - 1)

result = factorial(5)
"""
        vm = run(source, max_steps=200)
        assert vm.call_stack[0].local_vars["result"] == 120
        assert len(vm.closures) == 0
