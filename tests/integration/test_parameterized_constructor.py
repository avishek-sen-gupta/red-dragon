"""Tests for parameterized CALL_FUNCTION operand handling."""

from interpreter.type_expr import ScalarType
from interpreter.typed_value import TypedValue
from interpreter.run import run
from interpreter.constants import Language


class TestParameterizedCallFunction:
    def test_box_new_creates_box_object(self):
        """Box::new(n) creates a Box object wrapping n via __boxed__."""
        source = """\
struct Node { value: i32 }

let n = Node { value: 42 };
let b = Box::new(n);
"""
        vm = run(source, language=Language.RUST, max_steps=300)
        locals_ = {
            k: v.value if isinstance(v, TypedValue) else v
            for k, v in vm.call_stack[0].local_vars.items()
        }
        # Box::new creates a Box heap object
        b_addr = locals_["b"]
        assert b_addr in vm.heap
        box_obj = vm.heap[b_addr]
        assert box_obj.type_hint == ScalarType("Box")
        # The Box stores the inner Node via __boxed__
        assert "__boxed__" in box_obj.fields
        inner_addr = box_obj.fields["__boxed__"]
        inner_val = (
            inner_addr.value if isinstance(inner_addr, TypedValue) else inner_addr
        )
        assert inner_val == locals_["n"]

    def test_option_constructor_creates_heap_object(self):
        """Option(42) should create a HeapObject with Option type_hint."""
        source = "let opt = Some(42);"
        vm = run(source, language=Language.RUST, max_steps=300)
        locals_ = {
            k: v.value if isinstance(v, TypedValue) else v
            for k, v in vm.call_stack[0].local_vars.items()
        }
        opt_addr = locals_.get("opt")
        assert opt_addr in vm.heap
        opt_obj = vm.heap[opt_addr]
        assert opt_obj.type_hint == ScalarType("Option")
        assert "value" in opt_obj.fields
