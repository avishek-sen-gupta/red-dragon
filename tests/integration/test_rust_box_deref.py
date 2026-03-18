"""Integration tests for Rust Box auto-deref: Box::new → __method_missing__ → field delegation."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_rust(source: str, max_steps: int = 200):
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestBoxFieldDelegation:
    def test_box_field_access_delegates_to_inner(self):
        """box_val.field delegates to inner object's field via __method_missing__."""
        _, local_vars = _run_rust(
            """\
struct Point { x: i32, y: i32 }
let p = Point { x: 10, y: 20 };
let b = Box::new(p);
let answer = b.x;
""",
            max_steps=500,
        )
        assert local_vars["answer"] == 10

    def test_box_explicit_deref(self):
        """*box_val returns the inner value via LOAD_FIELD '__boxed__'."""
        _, local_vars = _run_rust(
            """\
struct Point { x: i32, y: i32 }
let p = Point { x: 10, y: 20 };
let b = Box::new(p);
let inner = *b;
let answer = inner.x;
""",
            max_steps=500,
        )
        assert local_vars["answer"] == 10


class TestBoxMultiLevel:
    def test_double_box_field_access(self):
        """Box<Box<T>> chains __method_missing__ through two levels."""
        _, local_vars = _run_rust(
            """\
struct Point { x: i32 }
let p = Point { x: 42 };
let b1 = Box::new(p);
let b2 = Box::new(b1);
let answer = b2.x;
""",
            max_steps=600,
        )
        assert local_vars["answer"] == 42


class TestBoxMethodDelegation:
    def test_box_method_call_delegates_to_inner(self):
        """box_val.method() delegates to inner object's method via __method_missing__."""
        _, local_vars = _run_rust(
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
        assert local_vars["answer"] == 42


class TestBoxOptionInteraction:
    def test_some_box_unwrap_field_access(self):
        """Some(Box::new(node)).unwrap().field works via __method_missing__."""
        _, local_vars = _run_rust(
            """\
struct Node { value: i32 }
let n = Node { value: 99 };
let opt = Some(Box::new(n));
let inner = opt.unwrap();
let answer = inner.value;
""",
            max_steps=600,
        )
        assert local_vars["answer"] == 99
