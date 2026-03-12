"""Integration tests for C function pointer end-to-end execution.

These tests verify the full pipeline: C source → tree-sitter parse →
IR lowering → VM execution, specifically for function pointer scenarios.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_c(source: str, max_steps: int = 500) -> dict:
    """Run a C program and return the top-level frame's local_vars."""
    vm = run(source, language=Language.C, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


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

    def test_array_of_function_pointers(self):
        """Function pointers stored in an array and called by index."""
        source = """\
int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }
int mul(int a, int b) { return a * b; }

int (*ops[3])(int, int) = {&add, &sub, &mul};
int r0 = (*ops[0])(10, 3);
int r1 = (*ops[1])(10, 3);
int r2 = (*ops[2])(10, 3);
"""
        vars_ = _run_c(source)
        assert vars_["r0"] == 13
        assert vars_["r1"] == 7
        assert vars_["r2"] == 30

    def test_function_pointer_in_struct(self):
        """Function pointer stored as a struct field and called via member access."""
        source = """\
int add(int a, int b) { return a + b; }

struct Calculator {
    int (*op)(int, int);
};

struct Calculator calc;
calc.op = &add;
int result = (*calc.op)(4, 5);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 9

    def test_conditional_function_pointer_selection(self):
        """Function pointer assigned conditionally via if/else inside a function."""
        source = """\
int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }

int compute(int choice, int x, int y) {
    int (*op)(int, int);
    if (choice == 1) { op = &add; }
    else { op = &sub; }
    return (*op)(x, y);
}

int r1 = compute(1, 10, 3);
int r2 = compute(0, 10, 3);
"""
        vars_ = _run_c(source)
        assert vars_["r1"] == 13
        assert vars_["r2"] == 7

    def test_nested_function_pointer_calls(self):
        """Result of one FP call used as argument to another: fp1(fp2(1,2), 3)."""
        source = """\
int add(int a, int b) { return a + b; }
int mul(int a, int b) { return a * b; }

int (*fp1)(int, int) = &mul;
int (*fp2)(int, int) = &add;
int result = (*fp1)((*fp2)(1, 2), 3);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 9

    def test_callback_chain(self):
        """Function pointer forwarded through two call layers."""
        source = """\
int add(int a, int b) { return a + b; }

int apply(int (*f)(int, int), int x, int y) {
    return (*f)(x, y);
}

int apply_twice(int (*f)(int, int), int x, int y) {
    int first = apply(f, x, y);
    int second = apply(f, first, y);
    return second;
}

int result = apply_twice(&add, 1, 5);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 11

    def test_function_pointer_reassignment_in_loop(self):
        """FP reassigned mid-loop: first iteration uses add, rest use mul."""
        source = """\
int add(int a, int b) { return a + b; }
int mul(int a, int b) { return a * b; }

int result = 1;
int (*op)(int, int) = &add;
int i = 0;
while (i < 3) {
    result = (*op)(result, 2);
    op = &mul;
    i = i + 1;
}
"""
        vars_ = _run_c(source)
        # iter 0: add(1,2)=3, op→mul
        # iter 1: mul(3,2)=6
        # iter 2: mul(6,2)=12
        assert vars_["result"] == 12

    def test_higher_order_function_pointer(self):
        """Function pointer parameter that itself takes a function pointer."""
        source = """\
int apply(int (*f)(int, int), int x, int y) {
    return (*f)(x, y);
}

int add(int a, int b) { return a + b; }

int meta_apply(int (*applier)(int (*)(int, int), int, int), int (*f)(int, int), int x, int y) {
    return (*applier)(f, x, y);
}

int result = meta_apply(&apply, &add, 3, 4);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 7

    def test_typedef_function_pointer(self):
        """Function pointer via typedef alias."""
        source = """\
typedef int (*binop)(int, int);

int add(int a, int b) { return a + b; }

binop get_add() { return &add; }

binop fp = get_add();
int result = (*fp)(6, 7);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 13

    def test_ternary_function_pointer_selection(self):
        """Ternary operator selecting between two function pointers."""
        source = """\
int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }

int x = 1;
int (*op)(int, int) = (x > 0) ? &add : &sub;
int r1 = (*op)(10, 3);

x = 0;
int (*op2)(int, int) = (x > 0) ? &add : &sub;
int r2 = (*op2)(10, 3);
"""
        vars_ = _run_c(source)
        assert vars_["r1"] == 13
        assert vars_["r2"] == 7

    def test_self_referencing_function_pointer(self):
        """Function obtains its own address via &name and calls itself through the FP."""
        source = """\
int factorial(int n) {
    if (n <= 1) { return 1; }
    int (*self)(int) = &factorial;
    return n * (*self)(n - 1);
}

int result = factorial(5);
"""
        vars_ = _run_c(source, max_steps=1000)
        assert vars_["result"] == 120
