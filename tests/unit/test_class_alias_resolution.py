"""Tests for class name dereference in new_object via variable store."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_js(source: str, max_steps: int = 200):
    vm = run(source, language=Language.JAVASCRIPT, max_steps=max_steps)
    return vm


class TestNewObjectDereference:
    """new_object should dereference variables to find the canonical class name."""

    def test_anon_class_heap_type_hint(self):
        """Heap object created via `new Foo()` where Foo holds an anonymous class
        should have the canonical class name as type_hint, not the variable name."""
        vm = _run_js("""
            const Foo = class { constructor() {} };
            let obj = new Foo();
            """)
        locals_ = dict(vm.call_stack[0].local_vars)
        addr = locals_["obj"]
        assert (
            vm.heap[addr].type_hint != "Foo"
        ), "type_hint should be the canonical class name, not the variable alias"

    def test_named_class_heap_type_hint(self):
        """Regular class declaration should still use its own name as type_hint."""
        vm = _run_js("""
            class Bar { constructor() {} }
            let obj = new Bar();
            """)
        locals_ = dict(vm.call_stack[0].local_vars)
        addr = locals_["obj"]
        assert vm.heap[addr].type_hint == "Bar"

    def test_reassigned_class_ref(self):
        """const B = A where A is a named class — new B() should resolve to A."""
        vm = _run_js("""
            class Original { constructor(x) { this.x = x; } }
            const Alias = Original;
            let obj = new Alias(42);
            let result = obj.x;
            """)
        locals_ = dict(vm.call_stack[0].local_vars)
        assert locals_["result"] == 42
