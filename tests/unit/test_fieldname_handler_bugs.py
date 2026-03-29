"""Regression tests for two FieldName-related bugs fixed in memory handlers.

Bug 1 (_infer_index_kind): Numeric string indices like "0", "1" must use
FieldKind.INDEX, not PROPERTY. Previously only isinstance(idx_val, int) was
checked, so a string index "0" would produce a PROPERTY key and miss the field.

Bug 2 (_handle_load_indirect — INDEX→PROPERTY fallback): LOAD_INDIRECT must
fall back from INDEX to PROPERTY kind when dereferencing a Box-style field
stored via store_field (which always writes PROPERTY kind at offset "0").
"""

from __future__ import annotations

import pytest

from interpreter.field_name import FieldName, FieldKind
from interpreter.var_name import VarName
from interpreter.ir import IRInstruction, Opcode
from interpreter.instructions import InstructionBase
from interpreter.address import Address
from interpreter.vm.vm_types import (
    HeapObject,
    Pointer,
    StackFrame,
    VMState,
    ExecutionResult,
    StateUpdate,
)
from interpreter.vm.vm import apply_update
from interpreter.func_name import FuncName
from interpreter.types.typed_value import TypedValue, typed_from_runtime, unwrap
from interpreter.register import Register
from interpreter.address import Address
from interpreter.vm.vm_types import SymbolicValue
from interpreter.vm.executor import (
    _handle_load_index,
    _handle_load_indirect,
    _default_handler_context,
)

_CTX = _default_handler_context()


def _make_vm() -> VMState:
    frame = StackFrame(function_name=FuncName("test"))
    return VMState(call_stack=[frame])


def _make_inst(
    opcode: Opcode, result_reg: str = "", operands: list = ()
) -> InstructionBase:
    return IRInstruction(
        opcode=opcode,
        result_reg=result_reg or None,
        operands=list(operands),
    )


def _apply(vm: VMState, result: ExecutionResult) -> None:
    apply_update(vm, result.update)


# ── Bug 1: numeric string indices use INDEX kind ──────────────────


class TestNumericStringIndexUsesIndexKind:
    def test_load_index_with_string_zero_finds_index_keyed_field(self):
        """LOAD_INDEX where index register holds string '0' must match a
        FieldName('0', INDEX) field — not return symbolic."""
        vm = _make_vm()
        vm.heap_set(
            Address("arr_0"),
            HeapObject(
                fields={FieldName("0", FieldKind.INDEX): typed_from_runtime(42)}
            ),
        )
        vm.current_frame.registers[Register("%arr")] = typed_from_runtime("arr_0")
        vm.current_frame.registers[Register("%idx")] = typed_from_runtime("0")

        inst = _make_inst(
            Opcode.LOAD_INDEX, result_reg=Register("%out"), operands=["%arr", "%idx"]
        )
        result = _handle_load_index(inst, vm, _CTX)
        _apply(vm, result)

        out = unwrap(vm.current_frame.registers[Register("%out")])
        assert out == 42

    def test_load_index_with_string_index_does_not_return_symbolic(self):
        """A string numeric index must resolve to the stored value, never symbolic."""
        vm = _make_vm()
        vm.heap_set(
            Address("arr_1"),
            HeapObject(
                fields={FieldName("3", FieldKind.INDEX): typed_from_runtime(99)}
            ),
        )
        vm.current_frame.registers[Register("%arr")] = typed_from_runtime("arr_1")
        vm.current_frame.registers[Register("%idx")] = typed_from_runtime("3")

        inst = _make_inst(
            Opcode.LOAD_INDEX, result_reg=Register("%out"), operands=["%arr", "%idx"]
        )
        result = _handle_load_index(inst, vm, _CTX)
        _apply(vm, result)

        out = unwrap(vm.current_frame.registers[Register("%out")])
        assert not isinstance(out, SymbolicValue)
        assert out == 99


# ── Bug 2: LOAD_INDIRECT falls back from INDEX to PROPERTY ───────


class TestLoadIndirectIndexToPropertyFallback:
    def test_load_indirect_finds_property_keyed_field_when_index_absent(self):
        """LOAD_INDIRECT must fall back to PROPERTY kind when no INDEX key
        exists at the pointer offset — simulating Box::new(value) layout."""
        vm = _make_vm()
        # Box stores its inner value via store_field → PROPERTY kind at "0"
        vm.heap_set(
            Address("box_0"),
            HeapObject(
                type_hint="Box",
                fields={FieldName("0", FieldKind.PROPERTY): typed_from_runtime(77)},
            ),
        )
        ptr = Pointer(base=Address("box_0"), offset=0)
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)

        inst = _make_inst(
            Opcode.LOAD_INDIRECT, result_reg=Register("%val"), operands=["%ptr"]
        )
        result = _handle_load_indirect(inst, vm, _CTX)
        _apply(vm, result)

        val = unwrap(vm.current_frame.registers[Register("%val")])
        assert val == 77

    def test_load_indirect_prefers_index_kind_when_both_present(self):
        """When both INDEX and PROPERTY fields exist at the same key, INDEX wins."""
        vm = _make_vm()
        vm.heap_set(
            Address("mem_0"),
            HeapObject(
                fields={
                    FieldName("0", FieldKind.INDEX): typed_from_runtime(10),
                    FieldName("0", FieldKind.PROPERTY): typed_from_runtime(20),
                }
            ),
        )
        ptr = Pointer(base=Address("mem_0"), offset=0)
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)

        inst = _make_inst(
            Opcode.LOAD_INDIRECT, result_reg=Register("%val"), operands=["%ptr"]
        )
        result = _handle_load_indirect(inst, vm, _CTX)
        _apply(vm, result)

        val = unwrap(vm.current_frame.registers[Register("%val")])
        assert val == 10

    def test_load_indirect_does_not_return_symbolic_for_property_field(self):
        """LOAD_INDIRECT on a Box-style heap object must not return symbolic."""
        vm = _make_vm()
        vm.heap_set(
            Address("box_1"),
            HeapObject(
                type_hint="Box",
                fields={
                    FieldName("0", FieldKind.PROPERTY): typed_from_runtime("hello")
                },
            ),
        )
        ptr = Pointer(base=Address("box_1"), offset=0)
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)

        inst = _make_inst(
            Opcode.LOAD_INDIRECT, result_reg=Register("%val"), operands=["%ptr"]
        )
        result = _handle_load_indirect(inst, vm, _CTX)
        _apply(vm, result)

        val = unwrap(vm.current_frame.registers[Register("%val")])
        assert not isinstance(val, SymbolicValue)
        assert val == "hello"
