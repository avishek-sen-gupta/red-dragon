"""Integration tests for Python frontend: future_import_statement."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


class TestPythonFutureImportExecution:
    def test_future_import_does_not_crash(self):
        """from __future__ import annotations should execute without errors."""
        vm = run(
            "from __future__ import annotations\nx = 42\nanswer = x",
            language=Language.PYTHON,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("answer")] == 42

    def test_future_import_with_arithmetic(self):
        """Future import followed by arithmetic should not interfere."""
        source = """\
from __future__ import annotations
x = 10
y = x + 5
answer = y
"""
        vm = run(
            source,
            language=Language.PYTHON,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("answer")] == 15


class TestPythonIdentityOperatorsExecution:
    def test_is_none_true(self):
        """'x is None' should evaluate to True when x is None."""
        vm = run(
            "x = None\nresult = x is None",
            language=Language.PYTHON,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] is True

    def test_is_none_false(self):
        """'x is None' should evaluate to False when x is not None."""
        vm = run(
            "x = 42\nresult = x is None",
            language=Language.PYTHON,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] is False

    def test_is_not_none_true(self):
        """'x is not None' should evaluate to True when x is not None."""
        vm = run(
            "x = 1\nresult = x is not None",
            language=Language.PYTHON,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] is True

    def test_is_not_none_false(self):
        """'x is not None' should evaluate to False when x is None."""
        vm = run(
            "x = None\nresult = x is not None",
            language=Language.PYTHON,
            max_steps=200,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] is False

    def test_not_in_list_true(self):
        """'5 not in [1, 2, 3]' should evaluate to True."""
        vm = run(
            "lst = [1, 2, 3]\nresult = 5 not in lst",
            language=Language.PYTHON,
            max_steps=500,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] is True

    def test_in_list_true(self):
        """'2 in [1, 2, 3]' should evaluate to True."""
        vm = run(
            "lst = [1, 2, 3]\nresult = 2 in lst",
            language=Language.PYTHON,
            max_steps=500,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] is True

    def test_in_list_false(self):
        """'5 in [1, 2, 3]' should evaluate to False."""
        vm = run(
            "lst = [1, 2, 3]\nresult = 5 in lst",
            language=Language.PYTHON,
            max_steps=500,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] is False

    def test_not_in_list_branch_taken(self):
        """'if x not in [1,2,3]: result = 99' should execute the branch when x=5."""
        source = """\
x = 5
if x not in [1, 2, 3]:
    result = 99
"""
        vm = run(
            source,
            language=Language.PYTHON,
            max_steps=500,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] == 99

    def test_not_in_list_branch_skipped(self):
        """'if x not in [1,2,3]: result = 99' should skip the branch when x=2."""
        source = """\
x = 2
result = 0
if x not in [1, 2, 3]:
    result = 99
"""
        vm = run(
            source,
            language=Language.PYTHON,
            max_steps=500,
            entry_point=EntryPoint.top_level(),
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars[VarName("result")] == 0
