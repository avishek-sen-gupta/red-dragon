"""Integration tests for C function pointer end-to-end execution.

These tests verify the full pipeline: C source → tree-sitter parse →
IR lowering → VM execution, specifically for function pointer scenarios.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_c(source: str, max_steps: int = 500) -> dict:
    """Run a C program and return the top-level frame's local_vars."""
    vm = run(source, language=Language.C, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestCFunctionPointerE2E:
    def test_basic_function_pointer_with_address_of_and_deref(self):
        """Classic C function pointer: &add assigned to fp, called via (*fp)."""
        source = """\
int add(int a, int b) { return a + b; }

int (*fp)(int, int) = &add;
int result = (*fp)(3, 5);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 8

    def test_function_pointer_swap(self):
        """Reassigning a function pointer changes which function is called."""
        source = """\
int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }

int (*op)(int, int) = &add;
int r1 = (*op)(10, 3);
op = &sub;
int r2 = (*op)(10, 3);
"""
        vars_ = _run_c(source)
        assert vars_["r1"] == 13
        assert vars_["r2"] == 7

    def test_function_pointer_passed_as_argument(self):
        """A function pointer passed to another function and called there."""
        source = """\
int add(int a, int b) { return a + b; }

int apply(int (*f)(int, int), int x, int y) {
    return (*f)(x, y);
}

int result = apply(&add, 7, 3);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 10

    def test_function_pointer_returned_from_function(self):
        """A function pointer returned from a function and called by the caller."""
        source = """\
int add(int a, int b) { return a + b; }

int apply_returned(int x, int y) {
    int (*fp)(int, int) = &add;
    return (*fp)(x, y);
}

int r1 = apply_returned(2, 3);
int r2 = apply_returned(10, 20);
"""
        vars_ = _run_c(source)
        assert vars_["r1"] == 5
        assert vars_["r2"] == 30

    def test_function_pointer_return_type_declaration(self):
        """Function with function-pointer return type: int (*get_op(int))(int, int).

        The complex C declaration nests the real function name and parameters
        inside a parenthesized_declarator. The frontend must find the innermost
        function_declarator to extract the correct parameter list.
        """
        source = """\
int add(int a, int b) { return a + b; }
int mul(int a, int b) { return a * b; }

int (*get_op(int choice))(int, int) {
    if (choice == 1) { return &add; }
    return &mul;
}

int (*fp1)(int, int) = get_op(1);
int r1 = (*fp1)(2, 3);
int (*fp2)(int, int) = get_op(0);
int r2 = (*fp2)(2, 3);
"""
        vars_ = _run_c(source)
        assert vars_["r1"] == 5, "get_op(1) should return &add: 2+3=5"
        assert vars_["r2"] == 6, "get_op(0) should return &mul: 2*3=6"
