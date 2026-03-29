"""Integration tests for Rust Box auto-deref: Box::new → __method_missing__ → field delegation."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.type_expr import scalar
from interpreter.types.typed_value import unwrap_locals
from interpreter.vm.vm_types import Pointer, SymbolicValue


def _run_rust(source: str, max_steps: int = 200):
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


def _typed_locals(vm):
    """Return raw TypedValue dict (not unwrapped) for type assertions."""
    return vm.call_stack[0].local_vars


class TestBoxFieldDelegation:
    def test_box_field_access_delegates_to_inner(self):
        """box_val.field delegates to inner object's field via __method_missing__."""
        vm, local_vars = _run_rust(
            """\
struct Point { x: i32, y: i32 }
let p = Point { x: 10, y: 20 };
let b = Box::new(p);
let answer = b.x;
""",
            max_steps=500,
        )
        assert local_vars[VarName("answer")] == 10
        assert _typed_locals(vm)[VarName("answer")].type == scalar("Int")
        assert vm.heap[str(local_vars[VarName("b")].base)].type_hint == "Box"
        assert vm.heap[str(local_vars[VarName("p")].base)].type_hint == "Point"

    def test_box_explicit_deref(self):
        """*box_val returns the inner value via LOAD_INDIRECT."""
        vm, local_vars = _run_rust(
            """\
struct Point { x: i32, y: i32 }
let p = Point { x: 10, y: 20 };
let b = Box::new(p);
let inner = *b;
let answer = inner.x;
""",
            max_steps=500,
        )
        assert local_vars[VarName("answer")] == 10
        assert _typed_locals(vm)[VarName("answer")].type == scalar("Int")
        # *b dereferences to the inner Point heap address
        assert vm.heap[str(local_vars[VarName("inner")].base)].type_hint == "Point"


class TestBoxMultiLevel:
    def test_double_box_field_access(self):
        """Box<Box<T>> chains __method_missing__ through two levels."""
        vm, local_vars = _run_rust(
            """\
struct Point { x: i32 }
let p = Point { x: 42 };
let b1 = Box::new(p);
let b2 = Box::new(b1);
let answer = b2.x;
""",
            max_steps=600,
        )
        assert local_vars[VarName("answer")] == 42
        assert _typed_locals(vm)[VarName("answer")].type == scalar("Int")
        assert vm.heap[str(local_vars[VarName("b1")].base)].type_hint == "Box"
        assert vm.heap[str(local_vars[VarName("b2")].base)].type_hint == "Box"


class TestBoxMethodDelegation:
    def test_box_method_call_delegates_to_inner(self):
        """box_val.method() delegates to inner object's method via __method_missing__."""
        vm, local_vars = _run_rust(
            """\
struct Counter { count: i32 }

impl Counter {
    fn get_count(&self) -> i32 {
        return self.count;
    }
}

let c = Counter { count: 42 };
let b = Box::new(c);
let answer = b.get_count();
""",
            max_steps=600,
        )
        assert local_vars[VarName("answer")] == 42
        assert _typed_locals(vm)[VarName("answer")].type == scalar("Int")
        assert vm.heap[str(local_vars[VarName("b")].base)].type_hint == "Box"
        assert vm.heap[str(local_vars[VarName("c")].base)].type_hint == "Counter"


class TestBoxMultiLevelMethodDelegation:
    def test_double_box_method_call(self):
        """Box<Box<Counter>> chains method delegation through two levels."""
        vm, local_vars = _run_rust(
            """\
struct Counter { count: i32 }

impl Counter {
    fn get_count(&self) -> i32 {
        return self.count;
    }
}

let c = Counter { count: 77 };
let b1 = Box::new(c);
let b2 = Box::new(b1);
let answer = b2.get_count();
""",
            max_steps=800,
        )
        assert local_vars[VarName("answer")] == 77
        assert _typed_locals(vm)[VarName("answer")].type == scalar("Int")
        assert vm.heap[str(local_vars[VarName("b2")].base)].type_hint == "Box"


class TestBoxChainedDeref:
    def test_chained_field_access_in_expression(self):
        """b.x + b.y — two auto-derefs in one arithmetic expression."""
        vm, local_vars = _run_rust(
            """\
struct Point { x: i32, y: i32 }
let p = Point { x: 3, y: 7 };
let b = Box::new(p);
let answer = b.x + b.y;
""",
            max_steps=600,
        )
        assert local_vars[VarName("answer")] == 10
        assert _typed_locals(vm)[VarName("answer")].type == scalar("Int")

    def test_nested_struct_field_through_box(self):
        """tree.left.value — Box in a struct field, then access inner field."""
        vm, local_vars = _run_rust(
            """\
struct Node { value: i32 }
struct Tree { left: Box<Node> }
let n = Node { value: 55 };
let t = Tree { left: Box::new(n) };
let boxed_node = t.left;
let answer = boxed_node.value;
""",
            max_steps=600,
        )
        assert local_vars[VarName("answer")] == 55
        assert _typed_locals(vm)[VarName("answer")].type == scalar("Int")
        assert vm.heap[str(local_vars[VarName("t")].base)].type_hint == "Tree"


class TestBoxNegativeCases:
    def test_missing_field_on_inner_returns_symbolic(self):
        """Accessing a field that doesn't exist on the inner struct produces symbolic, not crash."""
        vm, local_vars = _run_rust(
            """\
struct Point { x: i32 }
let p = Point { x: 10 };
let b = Box::new(p);
let answer = b.nonexistent;
""",
            max_steps=500,
        )
        assert isinstance(local_vars[VarName("answer")], SymbolicValue)
        assert vm.heap[str(local_vars[VarName("b")].base)].type_hint == "Box"

    def test_box_primitive_field_access_returns_symbolic(self):
        """Box::new(42) — accessing a field on a boxed primitive returns symbolic."""
        vm, local_vars = _run_rust(
            """\
let b = Box::new(42);
let answer = b.x;
""",
            max_steps=500,
        )
        assert isinstance(local_vars[VarName("answer")], SymbolicValue)
        assert vm.heap[str(local_vars[VarName("b")].base)].type_hint == "Box"


class TestBoxOptionInteraction:
    def test_some_box_unwrap_field_access(self):
        """Some(Box::new(node)).unwrap().field works via __method_missing__."""
        vm, local_vars = _run_rust(
            """\
struct Node { value: i32 }
let n = Node { value: 99 };
let opt = Some(Box::new(n));
let inner = opt.unwrap();
let answer = inner.value;
""",
            max_steps=600,
        )
        assert local_vars[VarName("answer")] == 99
        assert _typed_locals(vm)[VarName("answer")].type == scalar("Int")
