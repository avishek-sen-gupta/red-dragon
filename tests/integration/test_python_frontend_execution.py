"""Integration tests for Python frontend: future_import_statement."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


class TestPythonFutureImportExecution:
    def test_future_import_does_not_crash(self):
        """from __future__ import annotations should execute without errors."""
        vm = run(
            "from __future__ import annotations\nx = 42\nanswer = x",
            language=Language.PYTHON,
            max_steps=200,
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars["answer"] == 42

    def test_future_import_with_arithmetic(self):
        """Future import followed by arithmetic should not interfere."""
        source = """\
from __future__ import annotations
x = 10
y = x + 5
answer = y
"""
        vm = run(source, language=Language.PYTHON, max_steps=200)
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars["answer"] == 15
