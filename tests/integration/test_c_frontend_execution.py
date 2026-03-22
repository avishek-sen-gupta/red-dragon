"""Integration tests for C frontend: linkage_specification, struct initializer lists."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run_c(source: str, max_steps: int = 500) -> dict:
    vm = run(source, language=Language.C, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestCLinkageSpecificationExecution:
    def test_linkage_spec_does_not_crash(self):
        """extern 'C' block should execute without errors."""
        vm = run(
            'extern "C" { int x = 42; }\nint y = x + 1;',
            language=Language.C,
            max_steps=200,
        )
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars["y"] == 43

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
        local_vars = unwrap_locals(vm.call_stack[0].local_vars)
        assert local_vars["result"] == 7


class TestCStructPositionalInitExecution:
    """Positional struct initializer lists produce concrete field values."""

    def test_positional_init_field_access(self):
        """struct Node n = {3, 0}; n.value should return 3."""
        vars_ = _run_c("""\
struct Node { int value; int next; };
struct Node n = {3, 0};
int answer = n.value;
""")
        assert vars_["answer"] == 3

    def test_positional_init_second_field(self):
        """struct Node n = {3, 7}; n.next should return 7."""
        vars_ = _run_c("""\
struct Node { int value; int next; };
struct Node n = {3, 7};
int answer = n.next;
""")
        assert vars_["answer"] == 7

    def test_positional_init_linked_list(self):
        """Linked list built with positional initializers should allow
        field traversal to produce concrete sum."""
        vars_ = _run_c(
            """\
struct Node { int value; int next; };
struct Node n3 = {3, 0};
struct Node n2 = {2, 0};
struct Node n1 = {1, 0};
int answer = n1.value + n2.value + n3.value;
""",
            max_steps=500,
        )
        assert vars_["answer"] == 6


class TestCStructDesignatedInitExecution:
    """Designated struct initializer lists produce concrete field values."""

    def test_designated_init_field_access(self):
        """{.value = 42} should store and retrieve field concretely."""
        vars_ = _run_c("""\
struct Point { int x; int y; };
struct Point p = {.x = 42, .y = 10};
int answer = p.x;
""")
        assert vars_["answer"] == 42

    def test_designated_init_out_of_order(self):
        """Designated init can specify fields in any order."""
        vars_ = _run_c("""\
struct Point { int x; int y; };
struct Point p = {.y = 10, .x = 42};
int answer = p.x + p.y;
""")
        assert vars_["answer"] == 52


class TestCStructFieldStoreLoad:
    """Plain struct declaration + explicit field assignment + field read."""

    def test_struct_field_store_then_load(self):
        """struct Circle c; c.radius = 5; int result = c.radius; should return 5."""
        vars_ = _run_c("""\
struct Circle { int radius; };
struct Circle c;
c.radius = 5;
int result = c.radius;
""")
        assert isinstance(vars_["result"], int) and vars_["result"] == 5

    def test_struct_two_fields_store_then_load(self):
        """Storing two fields independently and reading both should return correct values."""
        vars_ = _run_c("""\
struct Point { int x; int y; };
struct Point p;
p.x = 10;
p.y = 20;
int sum = p.x + p.y;
""")
        assert isinstance(vars_["sum"], int) and vars_["sum"] == 30

    def test_struct_field_overwrite(self):
        """Overwriting a struct field should return the latest value."""
        vars_ = _run_c("""\
struct Box { int val; };
struct Box b;
b.val = 3;
b.val = 7;
int result = b.val;
""")
        assert isinstance(vars_["result"], int) and vars_["result"] == 7
