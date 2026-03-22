"""Integration tests for return_value TypedValue migration — end-to-end execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run_python(source: str, max_steps: int = 200):
    """Run a Python program and return the VM."""
    return run(source, language=Language.PYTHON, max_steps=max_steps)


class TestReturnValueTypedIntegration:
    """End-to-end tests verifying return values flow as TypedValue through the VM."""

    def test_function_returns_int(self):
        """Function returning an int stores TypedValue in caller's register."""
        vm = _run_python("""\
def add(a, b):
    return a + b
result = add(3, 4)
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["result"] == 7

    def test_function_returns_none(self):
        """Function returning None stores None value (not Void) in caller's register."""
        vm = _run_python("""\
def get_none():
    return None
result = get_none()
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["result"] is None

    def test_void_function_result_not_used(self):
        """Void function (no return) executes without error; other vars unaffected."""
        vm = _run_python("""\
x = 10
def side_effect():
    pass
side_effect()
y = x + 5
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["y"] == 15

    def test_function_returns_string(self):
        """Function returning a string stores TypedValue in caller's register."""
        vm = _run_python("""\
def greet(name):
    return "hello " + name
msg = greet("world")
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["msg"] == "hello world"
