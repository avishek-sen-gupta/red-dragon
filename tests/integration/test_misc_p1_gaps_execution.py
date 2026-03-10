"""Integration tests for miscellaneous P1 lowering gaps: C linkage_specification, Python future_import, Scala export_declaration.

Verifies end-to-end execution through the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


class TestCLinkageSpecificationExecution:
    def test_linkage_spec_does_not_crash(self):
        """extern 'C' block should execute without errors."""
        vm = run(
            'extern "C" { int x = 42; }\nint y = x + 1;',
            language=Language.C,
            max_steps=200,
        )
        local_vars = dict(vm.call_stack[0].local_vars)
        assert "y" in local_vars

    def test_linkage_spec_function_decl(self):
        """Function declared in extern 'C' should be callable."""
        source = """\
extern "C" {
    int add(int a, int b) {
        return a + b;
    }
}
int result = add(3, 4);
"""
        vm = run(source, language=Language.C, max_steps=300)
        local_vars = dict(vm.call_stack[0].local_vars)
        assert local_vars["result"] == 7


class TestPythonFutureImportExecution:
    def test_future_import_does_not_crash(self):
        """from __future__ import annotations should execute without errors."""
        vm = run(
            "from __future__ import annotations\nx = 42\nanswer = x",
            language=Language.PYTHON,
            max_steps=200,
        )
        local_vars = dict(vm.call_stack[0].local_vars)
        assert local_vars["answer"] == 42

    def test_future_import_with_class(self):
        """Future import followed by class definition should work."""
        source = """\
from __future__ import annotations
x = 10
y = x + 5
answer = y
"""
        vm = run(source, language=Language.PYTHON, max_steps=200)
        local_vars = dict(vm.call_stack[0].local_vars)
        assert local_vars["answer"] == 15


class TestScalaExportDeclarationExecution:
    def test_export_does_not_crash(self):
        """export declaration should execute without errors."""
        vm = run(
            "export foo._\nval x = 42",
            language=Language.SCALA,
            max_steps=200,
        )
        local_vars = dict(vm.call_stack[0].local_vars)
        assert local_vars["x"] == 42
