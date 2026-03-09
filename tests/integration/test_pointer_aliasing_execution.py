"""Integration tests for pointer aliasing — end-to-end C and Rust execution.

Verifies that pointer operations (address-of, dereference, assignment
through pointer, pointer arithmetic) produce correct results through
the full parse -> lower -> execute pipeline.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_c(source: str, max_steps: int = 300):
    """Run a C program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.C, max_steps=max_steps)
    return vm, dict(vm.call_stack[0].local_vars)


def _run_rust(source: str, max_steps: int = 300):
    """Run a Rust program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, dict(vm.call_stack[0].local_vars)


class TestPrimitivePointerAliasing:
    def test_write_through_pointer_updates_original(self):
        """*ptr = 99 should update x when ptr = &x."""
        vm, local_vars = _run_c("""\
int x = 42;
int *ptr = &x;
*ptr = 99;
int answer = x;
""")
        assert local_vars["answer"] == 99

    def test_read_through_pointer(self):
        """*ptr should read the value of x."""
        vm, local_vars = _run_c("""\
int x = 42;
int *ptr = &x;
int answer = *ptr;
""")
        assert local_vars["answer"] == 42

    def test_modify_original_visible_through_pointer(self):
        """Changing x after &x should be visible through *ptr."""
        vm, local_vars = _run_c("""\
int x = 42;
int *ptr = &x;
x = 100;
int answer = *ptr;
""")
        assert local_vars["answer"] == 100


class TestPointerArithmeticExecution:
    def test_array_pointer_arithmetic(self):
        """*(ptr + 1) should access the next array element."""
        vm, local_vars = _run_c("""\
int arr[3] = {10, 20, 30};
int *ptr = arr;
int answer = *(ptr + 1);
""")
        assert local_vars["answer"] == 20


class TestPointerSubtractionExecution:
    def test_pointer_difference(self):
        """p2 - p1 should return the element distance."""
        vm, local_vars = _run_c("""\
int arr[4] = {10, 20, 30, 40};
int *p1 = arr;
int *p2 = arr;
p2 = p2 + 3;
int diff = p2 - p1;
""")
        assert local_vars["diff"] == 3


class TestPointerComparisonExecution:
    def test_pointer_less_than(self):
        """p1 < p2 should be true when p1 points before p2."""
        vm, local_vars = _run_c("""\
int arr[3] = {10, 20, 30};
int *p1 = arr;
int *p2 = p1 + 2;
int lt = p1 < p2;
""")
        assert local_vars["lt"] == True

    def test_pointer_greater_equal(self):
        """p2 >= p1 should be true when p2 points at or after p1."""
        vm, local_vars = _run_c("""\
int arr[3] = {10, 20, 30};
int *p1 = arr;
int *p2 = p1 + 1;
int ge = p2 >= p1;
int ge_eq = p1 >= p1;
""")
        assert local_vars["ge"] == True
        assert local_vars["ge_eq"] == True


class TestNestedPointerExecution:
    def test_double_pointer_write(self):
        """**pp = 99 should update x through two levels of indirection."""
        vm, local_vars = _run_c("""\
int x = 42;
int *ptr = &x;
int **pp = &ptr;
**pp = 99;
int answer = x;
""")
        assert local_vars["answer"] == 99


# ── Rust source-level integration tests ──────────────────────────


class TestRustReferenceRead:
    def test_read_through_reference(self):
        """let ptr = &x; *ptr should read x's value."""
        vm, local_vars = _run_rust("""\
let x = 42;
let ptr = &x;
let answer = *ptr;
""")
        assert local_vars["answer"] == 42


class TestRustMutableReferenceWrite:
    def test_write_through_mutable_reference_updates_original(self):
        """*ptr = 99 should update x when ptr = &mut x."""
        vm, local_vars = _run_rust("""\
let mut x = 42;
let ptr = &mut x;
*ptr = 99;
let answer = x;
""")
        assert local_vars["answer"] == 99

    def test_modify_original_visible_through_reference(self):
        """Changing x after &x should be visible through *ptr."""
        vm, local_vars = _run_rust("""\
let mut x = 42;
let ptr = &x;
x = 100;
let answer = *ptr;
""")
        assert local_vars["answer"] == 100
