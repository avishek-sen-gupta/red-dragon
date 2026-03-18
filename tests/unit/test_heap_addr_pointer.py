"""Tests for _heap_addr() Pointer support and ADDRESS_OF guard."""

from interpreter.vm import _heap_addr, HeapObject, VMState
from interpreter.vm_types import Pointer, StackFrame, SymbolicValue
from interpreter.ir import IRInstruction, Opcode
from interpreter.executor import _handle_address_of
from interpreter.typed_value import typed
from interpreter.type_expr import scalar
from interpreter.constants import TypeName


class TestHeapAddrPointer:
    def test_extracts_base_from_pointer(self):
        p = Pointer(base="obj_0", offset=0)
        assert _heap_addr(p) == "obj_0"

    def test_extracts_base_from_pointer_with_offset(self):
        p = Pointer(base="arr_5", offset=3)
        assert _heap_addr(p) == "arr_5"

    def test_still_handles_bare_string(self):
        assert _heap_addr("obj_0") == "obj_0"

    def test_still_handles_symbolic_value(self):
        sym = SymbolicValue(name="sym_0")
        assert _heap_addr(sym) == "sym_0"

    def test_returns_empty_for_int(self):
        assert _heap_addr(42) == ""


class TestAddressOfPointerGuard:
    """ADDRESS_OF on a Pointer variable must promote the Pointer itself to a
    new heap slot (double-indirection), NOT re-wrap its base address."""

    def test_address_of_pointer_produces_new_heap_slot(self):
        # Set up: variable "ptr" holds a Pointer whose base IS on the heap.
        # Without the guard, _heap_addr would return "obj_0" and the handler
        # would short-circuit to wrap that base — wrong for &ptr semantics.
        existing_ptr = Pointer(base="obj_0", offset=0)
        frame = StackFrame(
            function_name="main",
            local_vars={
                "ptr": typed(existing_ptr, scalar(TypeName.POINTER)),
            },
        )
        vm = VMState(
            call_stack=[frame],
            heap={
                "obj_0": HeapObject(
                    type_hint="SomeStruct",
                    fields={"x": typed(42, scalar(TypeName.INT))},
                ),
            },
        )

        inst = IRInstruction(
            opcode=Opcode.ADDRESS_OF,
            result_reg="t0",
            operands=["ptr"],
        )

        result = _handle_address_of(inst, vm)

        # The result must be a Pointer to a NEW heap slot (mem_*), not obj_0.
        result_ptr = result.update.register_writes["t0"].value
        assert isinstance(result_ptr, Pointer)
        assert result_ptr.base.startswith(
            "mem_"
        ), f"Expected a new mem_ heap slot for &ptr, got {result_ptr.base}"
        assert result_ptr.base != "obj_0"
        # The new heap slot must contain the original Pointer as its value.
        assert result_ptr.base in vm.heap
        promoted_val = vm.heap[result_ptr.base].fields["0"].value
        assert isinstance(promoted_val, Pointer)
        assert promoted_val.base == "obj_0"
