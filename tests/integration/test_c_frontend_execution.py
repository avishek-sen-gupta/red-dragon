"""Integration tests for C frontend: linkage_specification."""

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
