"""Integration tests for C struct pointer end-to-end execution.

These tests verify the full pipeline: C source → tree-sitter parse →
IR lowering → VM execution, specifically for struct pointer scenarios
including arrow operator, pass-by-pointer, and linked structures.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_c(source: str, max_steps: int = 500) -> dict:
    """Run a C program and return the top-level frame's local_vars."""
    vm = run(source, language=Language.C, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestCStructPointerE2E:
    def test_struct_pointer_read_and_write(self):
        """Basic struct pointer: &, ->, read/write through pointer."""
        source = """\
struct Point { int x; int y; };
struct Point pt;
pt.x = 10;
pt.y = 20;
struct Point *p = &pt;
p->x = 100;
int rx = pt.x;
int ry = p->y;
"""
        vars_ = _run_c(source)
        assert vars_["rx"] == 100
        assert vars_["ry"] == 20

    def test_struct_pointer_passed_to_function(self):
        """A function that mutates a struct through a pointer argument."""
        source = """\
struct Point { int x; int y; };

void translate(struct Point *p, int dx, int dy) {
    p->x = p->x + dx;
    p->y = p->y + dy;
}

struct Point pt;
pt.x = 5;
pt.y = 10;
translate(&pt, 3, 7);
int rx = pt.x;
int ry = pt.y;
"""
        vars_ = _run_c(source)
        assert vars_["rx"] == 8
        assert vars_["ry"] == 17

    def test_linked_struct_traversal(self):
        """Linked list nodes: n2.next = &n1, access n2.next->val."""
        source = """\
struct Node { int val; };

struct Node n1;
n1.val = 10;

struct Node n2;
n2.val = 20;
n2.next = &n1;

int v1 = n2.val;
int v2 = n2.next->val;
"""
        vars_ = _run_c(source)
        assert vars_["v1"] == 20
        assert vars_["v2"] == 10

    def test_struct_pointer_reassignment(self):
        """Reassigning a struct pointer to a different struct."""
        source = """\
struct Pair { int a; int b; };

struct Pair p1;
p1.a = 1;
p1.b = 2;

struct Pair p2;
p2.a = 10;
p2.b = 20;

struct Pair *ptr = &p1;
int r1 = ptr->a;
ptr = &p2;
int r2 = ptr->a;
"""
        vars_ = _run_c(source)
        assert vars_["r1"] == 1
        assert vars_["r2"] == 10

    def test_function_returns_modified_field(self):
        """A function reads a struct field via pointer and returns a value."""
        source = """\
struct Rect { int w; int h; };

int area(struct Rect *r) {
    return r->w * r->h;
}

struct Rect rect;
rect.w = 6;
rect.h = 7;
int result = area(&rect);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 42
