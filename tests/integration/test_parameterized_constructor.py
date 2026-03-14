"""Tests for parameterized CALL_FUNCTION operand handling."""

import pytest

from interpreter.type_expr import ScalarType, ParameterizedType
from interpreter.typed_value import TypedValue
from interpreter.run import run
from interpreter.constants import Language


class TestParameterizedCallFunction:
    @pytest.mark.xfail(
        reason="Requires prelude emission (Task 4) and Box::new lowering (Task 5)"
    )
    def test_box_node_constructor_creates_heap_object(self):
        """CALL_FUNCTION 'Box[Node]' should look up 'Box' in scope
        and create a HeapObject with ParameterizedType type_hint."""
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
        # b should be a heap address
        b_addr = locals_.get("b")
        assert b_addr is not None
        assert b_addr in vm.heap
        box_obj = vm.heap[b_addr]
        assert "value" in box_obj.fields

    @pytest.mark.xfail(
        reason="Requires prelude emission (Task 4) and Box::new lowering (Task 5)"
    )
    def test_parameterized_type_hint_on_heap_object(self):
        """Box[Node] constructor should produce HeapObject with
        ParameterizedType('Box', (ScalarType('Node'),)) type_hint."""
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
        b_addr = locals_.get("b")
        assert b_addr in vm.heap
        box_obj = vm.heap[b_addr]
        assert isinstance(box_obj.type_hint, ParameterizedType)
        assert box_obj.type_hint.constructor == "Box"
