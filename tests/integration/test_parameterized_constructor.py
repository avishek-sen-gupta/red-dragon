"""Tests for parameterized CALL_FUNCTION operand handling."""

from interpreter.type_expr import ScalarType
from interpreter.typed_value import TypedValue
from interpreter.run import run
from interpreter.constants import Language


class TestParameterizedCallFunction:
    def test_box_new_is_pass_through(self):
        """Box::new(n) is a pass-through — b and n point to the same object."""
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
        # Box::new is pass-through: b and n are the same heap address
        assert locals_["b"] == locals_["n"]
        # The heap object is the Node, not a Box
        b_addr = locals_["b"]
        assert b_addr in vm.heap
        assert vm.heap[b_addr].type_hint == ScalarType("Node")

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
