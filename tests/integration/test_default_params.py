"""Integration tests for default parameter resolution — end-to-end VM execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_python(source: str, max_steps: int = 500) -> tuple:
    """Run a Python program and return (vm, unwrapped local vars)."""
    vm = run(source, language=Language.PYTHON, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestPythonDefaultParamExecution:
    """End-to-end default parameter tests via VM execution."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run_python("""\
def two_fer(name="you"):
    return "One for " + name + ", one for me."

answer = two_fer()""")
        assert vars_["answer"] == "One for you, one for me."

    def test_string_default_overridden_by_arg(self):
        _, vars_ = _run_python("""\
def two_fer(name="you"):
    return "One for " + name + ", one for me."

answer = two_fer("Alice")""")
        assert vars_["answer"] == "One for Alice, one for me."

    def test_integer_default(self):
        _, vars_ = _run_python("""\
def add_one(x=42):
    return x + 1

answer = add_one()""")
        assert vars_["answer"] == 43

    def test_integer_default_overridden(self):
        _, vars_ = _run_python("""\
def add_one(x=42):
    return x + 1

answer = add_one(10)""")
        assert vars_["answer"] == 11

    def test_mixed_required_and_default(self):
        _, vars_ = _run_python("""\
def greet(greeting, name="world"):
    return greeting + " " + name

answer = greet("hello")""")
        assert vars_["answer"] == "hello world"

    def test_mixed_required_and_default_both_provided(self):
        _, vars_ = _run_python("""\
def greet(greeting, name="world"):
    return greeting + " " + name

answer = greet("hi", "Alice")""")
        assert vars_["answer"] == "hi Alice"

    def test_multiple_defaults(self):
        _, vars_ = _run_python("""\
def pair(a="x", b="y"):
    return a + b

answer = pair()""")
        assert vars_["answer"] == "xy"

    def test_multiple_defaults_first_overridden(self):
        _, vars_ = _run_python("""\
def pair(a="x", b="y"):
    return a + b

answer = pair("A")""")
        assert vars_["answer"] == "Ay"

    def test_lambda_default_param(self):
        _, vars_ = _run_python("""\
f = lambda x="hi": x
answer = f()""")
        assert vars_["answer"] == "hi"

    def test_function_without_defaults_unchanged(self):
        _, vars_ = _run_python("""\
def add(a, b):
    return a + b

answer = add(3, 4)""")
        assert vars_["answer"] == 7
