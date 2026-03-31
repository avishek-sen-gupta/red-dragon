"""Tests for run_linked() — execute a LinkedProgram with EntryPoint."""

from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run


class TestRunViaEntryPoint:
    """Test run() with new EntryPoint parameter (delegates to run_linked internally)."""

    def test_top_level_execution(self):
        source = "x = 10\ny = x + 5\n"
        vm = run(source, language=Language.PYTHON, entry_point=EntryPoint.top_level())
        assert vm.current_frame.local_vars[VarName("x")].value == 10
        assert vm.current_frame.local_vars[VarName("y")].value == 15

    def test_function_entry_point(self):
        source = """
def add(a, b):
    return a + b

def main():
    result = add(3, 7)
"""
        vm = run(
            source,
            language=Language.PYTHON,
            entry_point=EntryPoint.function(lambda f: f.name == FuncName("main")),
            max_steps=50,
        )
        assert vm.current_frame.local_vars[VarName("result")].value == 10

    def test_no_match_raises(self):
        source = "x = 1\n"
        import pytest

        with pytest.raises(ValueError, match="No function matched"):
            run(
                source,
                language=Language.PYTHON,
                entry_point=EntryPoint.function(
                    lambda f: f.name == FuncName("nonexistent")
                ),
            )
