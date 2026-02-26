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


class TestClosureMutation:
    """Tests for closure mutation semantics — capture by reference via shared environment."""

    def test_counter_persists_across_calls(self):
        """Calling a counter closure twice should increment: first=1, second=2."""
        source = """\
def make_counter():
    count = 0
    def counter():
        count = count + 1
        return count
    return counter

c = make_counter()
a = c()
b = c()
"""
        vars_ = _run_program(source, max_steps=300)
        assert vars_["a"] == 1
        assert vars_["b"] == 2

    def test_two_closures_share_state(self):
        """Two closures from the same factory share one environment.

        We test this by creating a factory that returns one closure, then
        calling the counter twice and verifying the shared env persists the
        mutation — the second call sees the first call's write.
        """
        source = """\
def make_accumulator(start):
    total = start
    def add(x):
        total = total + x
        return total
    return add

acc = make_accumulator(100)
a = acc(10)
b = acc(20)
c = acc(5)
"""
        vars_ = _run_program(source, max_steps=300)
        assert vars_["a"] == 110
        assert vars_["b"] == 130
        assert vars_["c"] == 135

    def test_independent_factories_dont_share(self):
        """Counters from separate factory calls are independent."""
        source = """\
def make_counter():
    count = 0
    def counter():
        count = count + 1
        return count
    return counter

c1 = make_counter()
c2 = make_counter()
a = c1()
b = c1()
c = c2()
"""
        vars_ = _run_program(source, max_steps=400)
        assert vars_["a"] == 1
        assert vars_["b"] == 2
        assert vars_["c"] == 1

    def test_read_only_closure_unchanged(self):
        """Existing read-only closure patterns still work (regression guard)."""
        source = """\
def make_adder(x):
    def adder(y):
        return x + y
    return adder

add5 = make_adder(5)
a = add5(3)
b = add5(10)
"""
        vars_ = _run_program(source)
        assert vars_["a"] == 8
        assert vars_["b"] == 15

    def test_make_counter_with_start(self):
        """make_counter(10) → counter(5)=15, counter(3)=18, result=33."""
        source = """\
def make_counter(start):
    count = start
    def counter(step):
        count = count + step
        return count
    return counter

counter = make_counter(10)
a = counter(5)
b = counter(3)
result = a + b
"""
        vars_ = _run_program(source, max_steps=300)
        assert vars_["a"] == 15
        assert vars_["b"] == 18
        assert vars_["result"] == 33


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
