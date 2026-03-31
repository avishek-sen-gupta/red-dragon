"""Tests for parameterized CALL_FUNCTION operand handling."""

from interpreter.address import Address
from interpreter.field_name import FieldName, FieldKind
from interpreter.var_name import VarName
from interpreter.types.type_expr import ScalarType
from interpreter.types.typed_value import TypedValue
from interpreter.run import run
from interpreter.constants import Language
from interpreter.project.entry_point import EntryPoint


class TestParameterizedCallFunction:
    def test_box_new_creates_box_object(self):
        """Box::new(n) creates a Box object wrapping n via field '0'."""
        source = """\
struct Node { value: i32 }

let n = Node { value: 42 };
let b = Box::new(n);
"""
        vm = run(
            source,
            language=Language.RUST,
            max_steps=300,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = {
            k: v.value if isinstance(v, TypedValue) else v
            for k, v in vm.call_stack[0].local_vars.items()
        }
        # Box::new creates a Box heap object
        b_ptr = locals_[VarName("b")]
        assert vm.heap_contains(b_ptr.base)
        box_obj = vm.heap_get(b_ptr.base)
        assert box_obj.type_hint == ScalarType("Box")
        # The Box stores the inner Node via field "0" (PROPERTY kind)
        assert FieldName("0") in box_obj.fields
        inner_addr = box_obj.fields[FieldName("0")]
        inner_val = (
            inner_addr.value if isinstance(inner_addr, TypedValue) else inner_addr
        )
        assert inner_val == locals_[VarName("n")]  # Both are Pointers now

    def test_option_constructor_creates_heap_object(self):
        """Option(42) should create a HeapObject with Option type_hint."""
        source = "let opt = Some(42);"
        vm = run(
            source,
            language=Language.RUST,
            max_steps=300,
            entry_point=EntryPoint.top_level(),
        )
        locals_ = {
            k: v.value if isinstance(v, TypedValue) else v
            for k, v in vm.call_stack[0].local_vars.items()
        }
        opt_ptr = locals_.get(VarName("opt"))
        assert vm.heap_contains(opt_ptr.base)
        opt_obj = vm.heap_get(opt_ptr.base)
        assert opt_obj.type_hint == ScalarType("Option")
        assert FieldName("value") in opt_obj.fields
