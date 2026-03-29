"""Unit tests for pointer aliasing — promote-on-address-of model.

Covers:
  1. Pointer dataclass basics (creation, arithmetic, equality)
  2. ADDRESS_OF opcode handler (promotes variable to heap, returns Pointer)
  3. Alias-aware LOAD_VAR / STORE_VAR (reads/writes go through heap)
  4. LOAD_INDIRECT/STORE_INDIRECT on Pointer (dereference read/write)
  5. BINOP pointer arithmetic (Pointer + int, Pointer - int)
  6. Nested pointers (int **pp = &ptr)
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
from interpreter.vm.executor import (
    _handle_address_of,
    _handle_load_var,
    _handle_store_var,
    _handle_load_field,
    _handle_store_field,
    _handle_load_indirect,
    _handle_store_indirect,
    _handle_binop,
    _handle_unop,
    _default_handler_context,
)

_CTX = _default_handler_context()


def _make_vm(**local_vars: object) -> VMState:
    """Create a VMState with a single frame containing the given local vars."""
    typed_vars = {VarName(k): typed_from_runtime(v) for k, v in local_vars.items()}
    frame = StackFrame(function_name=FuncName("test"), local_vars=typed_vars)
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
    """Apply an ExecutionResult's state update to the VM."""
    apply_update(vm, result.update)


# ── Pointer dataclass ─────────────────────────────────────────────


class TestPointerDataclass:
    def test_pointer_creation(self):
        p = Pointer(base=Address("mem_0"), offset=0)
        assert p.base == Address("mem_0")
        assert p.offset == 0

    def test_pointer_with_offset(self):
        p = Pointer(base=Address("mem_0"), offset=3)
        assert p.offset == 3

    def test_pointer_equality(self):
        assert Pointer(Address("mem_0"), 0) == Pointer(Address("mem_0"), 0)
        assert Pointer(Address("mem_0"), 0) != Pointer(Address("mem_0"), 1)
        assert Pointer(Address("mem_0"), 0) != Pointer(Address("mem_1"), 0)

    def test_pointer_is_frozen(self):
        p = Pointer(Address("mem_0"), 0)
        with pytest.raises(AttributeError):
            p.offset = 5


# ── ADDRESS_OF handler ────────────────────────────────────────────


class TestAddressOfHandler:
    def test_promotes_primitive_to_heap(self):
        """ADDRESS_OF 'x' should move x=42 to a HeapObject and return a Pointer."""
        vm = _make_vm(x=42)
        inst = _make_inst(Opcode.ADDRESS_OF, result_reg="%0", operands=["x"])
        result = _handle_address_of(inst, vm, _CTX)

        assert result.handled
        _apply(vm, result)

        # Result register should hold a Pointer
        ptr = unwrap(vm.current_frame.registers[Register("%0")])
        assert isinstance(ptr, Pointer)
        assert ptr.offset == 0

        # The variable should be aliased
        assert VarName("x") in vm.current_frame.var_heap_aliases

        # The heap object should hold the original value
        alias_ptr = vm.current_frame.var_heap_aliases[VarName("x")]
        assert (
            vm.heap_get(alias_ptr.base).fields[FieldName("0", FieldKind.INDEX)].value
            == 42
        )

    def test_second_address_of_returns_same_pointer(self):
        """Taking &x twice should return the same Pointer (same heap object)."""
        vm = _make_vm(x=42)
        inst = _make_inst(Opcode.ADDRESS_OF, result_reg="%0", operands=["x"])
        result1 = _handle_address_of(inst, vm, _CTX)
        _apply(vm, result1)

        inst2 = _make_inst(Opcode.ADDRESS_OF, result_reg="%1", operands=["x"])
        result2 = _handle_address_of(inst2, vm, _CTX)
        _apply(vm, result2)

        ptr1 = unwrap(vm.current_frame.registers[Register("%0")])
        ptr2 = unwrap(vm.current_frame.registers[Register("%1")])
        assert ptr1 == ptr2

    def test_address_of_struct_returns_pointer_to_existing_heap(self):
        """ADDRESS_OF on a variable holding a heap address should wrap it in a Pointer."""
        vm = _make_vm(s="obj_0")
        vm.heap_set(
            Address("obj_0"),
            HeapObject(
                type_hint="Point",
                fields={
                    k: typed_from_runtime(v)
                    for k, v in {FieldName("x"): 10, FieldName("y"): 20}.items()
                },
            ),
        )
        inst = _make_inst(Opcode.ADDRESS_OF, result_reg="%0", operands=["s"])
        result = _handle_address_of(inst, vm, _CTX)
        _apply(vm, result)

        ptr = unwrap(vm.current_frame.registers[Register("%0")])
        assert isinstance(ptr, Pointer)
        assert ptr.base == Address("obj_0")
        assert ptr.offset == 0


# ── Alias-aware LOAD_VAR / STORE_VAR ─────────────────────────────


class TestAliasAwareLoadStore:
    def _promote(self, vm: VMState, var_name: str) -> Pointer:
        """Helper: promote a variable via ADDRESS_OF and return the Pointer."""
        inst = _make_inst(Opcode.ADDRESS_OF, result_reg="%ptr", operands=[var_name])
        result = _handle_address_of(inst, vm, _CTX)
        _apply(vm, result)
        return unwrap(vm.current_frame.registers[Register("%ptr")])

    def test_load_var_reads_from_heap_when_aliased(self):
        """After &x, LOAD_VAR 'x' should read from the heap object."""
        vm = _make_vm(x=42)
        self._promote(vm, "x")

        # Directly modify the heap to simulate *ptr = 99
        alias = vm.current_frame.var_heap_aliases[VarName("x")]
        vm.heap_get(alias.base).fields[FieldName("0", FieldKind.INDEX)] = (
            typed_from_runtime(99)
        )

        inst = _make_inst(Opcode.LOAD_VAR, result_reg="%val", operands=["x"])
        result = _handle_load_var(inst, vm, _CTX)
        _apply(vm, result)

        assert unwrap(vm.current_frame.registers[Register("%val")]) == 99

    def test_store_var_writes_to_heap_when_aliased(self):
        """After &x, STORE_VAR 'x' should write to the heap object."""
        vm = _make_vm(x=42)
        ptr = self._promote(vm, "x")

        # Store a new value into x
        vm.current_frame.registers[Register("%newval")] = typed_from_runtime(77)
        inst = _make_inst(Opcode.STORE_VAR, operands=["x", "%newval"])
        result = _handle_store_var(inst, vm, _CTX)
        _apply(vm, result)

        # The heap should reflect the new value
        assert vm.heap_get(ptr.base).fields[FieldName("0", FieldKind.INDEX)].value == 77

    def test_store_via_pointer_then_load_var(self):
        """*ptr = 99 then read x should see 99."""
        vm = _make_vm(x=42)
        ptr = self._promote(vm, "x")

        # Write through pointer: STORE_INDIRECT ptr, 99
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)
        vm.current_frame.registers[Register("%99")] = typed_from_runtime(99)
        store_inst = _make_inst(Opcode.STORE_INDIRECT, operands=["%ptr", "%99"])
        store_result = _handle_store_indirect(store_inst, vm, _CTX)
        _apply(vm, store_result)

        # Now LOAD_VAR x should see 99
        load_inst = _make_inst(Opcode.LOAD_VAR, result_reg="%val", operands=["x"])
        load_result = _handle_load_var(load_inst, vm, _CTX)
        _apply(vm, load_result)

        assert unwrap(vm.current_frame.registers[Register("%val")]) == 99


# ── Dereference via LOAD_INDIRECT / STORE_INDIRECT ────────────────


class TestPointerDereference:
    def _promote(self, vm: VMState, var_name: str) -> Pointer:
        inst = _make_inst(Opcode.ADDRESS_OF, result_reg="%ptr", operands=[var_name])
        result = _handle_address_of(inst, vm, _CTX)
        _apply(vm, result)
        return unwrap(vm.current_frame.registers[Register("%ptr")])

    def test_load_indirect_reads_through_pointer(self):
        """LOAD_INDIRECT ptr should read from heap[str(ptr.base)].fields[str(ptr.offset)]."""
        vm = _make_vm(x=42)
        ptr = self._promote(vm, "x")
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)

        inst = _make_inst(Opcode.LOAD_INDIRECT, result_reg="%val", operands=["%ptr"])
        result = _handle_load_indirect(inst, vm, _CTX)
        _apply(vm, result)

        assert unwrap(vm.current_frame.registers[Register("%val")]) == 42

    def test_store_indirect_writes_through_pointer(self):
        """STORE_INDIRECT ptr, 99 should write to heap."""
        vm = _make_vm(x=42)
        ptr = self._promote(vm, "x")
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)
        vm.current_frame.registers[Register("%99")] = typed_from_runtime(99)

        inst = _make_inst(Opcode.STORE_INDIRECT, operands=["%ptr", "%99"])
        result = _handle_store_indirect(inst, vm, _CTX)
        _apply(vm, result)

        assert vm.heap_get(ptr.base).fields[FieldName("0", FieldKind.INDEX)].value == 99


# ── Pointer arithmetic ───────────────────────────────────────────


class TestPointerArithmetic:
    def test_pointer_plus_int(self):
        """Pointer + int should produce Pointer with adjusted offset."""
        vm = _make_vm()
        ptr = Pointer(Address("mem_0"), 0)
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)
        vm.current_frame.registers[Register("%3")] = typed_from_runtime(3)

        inst = _make_inst(
            Opcode.BINOP, result_reg="%result", operands=["+", "%ptr", "%3"]
        )
        result = _handle_binop(inst, vm, _CTX)
        _apply(vm, result)

        new_ptr = unwrap(vm.current_frame.registers[Register("%result")])
        assert isinstance(new_ptr, Pointer)
        assert new_ptr.base == Address("mem_0")
        assert new_ptr.offset == 3

    def test_int_plus_pointer(self):
        """int + Pointer should also produce Pointer (commutative)."""
        vm = _make_vm()
        ptr = Pointer(Address("mem_0"), 2)
        vm.current_frame.registers[Register("%2")] = typed_from_runtime(2)
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)

        inst = _make_inst(
            Opcode.BINOP, result_reg="%result", operands=["+", "%2", "%ptr"]
        )
        result = _handle_binop(inst, vm, _CTX)
        _apply(vm, result)

        new_ptr = unwrap(vm.current_frame.registers[Register("%result")])
        assert isinstance(new_ptr, Pointer)
        assert new_ptr.base == Address("mem_0")
        assert new_ptr.offset == 4

    def test_pointer_minus_int(self):
        """Pointer - int should produce Pointer with decreased offset."""
        vm = _make_vm()
        ptr = Pointer(Address("mem_0"), 5)
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)
        vm.current_frame.registers[Register("%2")] = typed_from_runtime(2)

        inst = _make_inst(
            Opcode.BINOP, result_reg="%result", operands=["-", "%ptr", "%2"]
        )
        result = _handle_binop(inst, vm, _CTX)
        _apply(vm, result)

        new_ptr = unwrap(vm.current_frame.registers[Register("%result")])
        assert isinstance(new_ptr, Pointer)
        assert new_ptr.base == Address("mem_0")
        assert new_ptr.offset == 3

    def test_pointer_arithmetic_then_deref(self):
        """(ptr + 1) then LOAD_INDIRECT should read offset 1 from the heap."""
        vm = _make_vm()
        # Set up a heap array with 3 elements
        vm.heap_set(
            Address("arr_0"),
            HeapObject(
                fields={
                    k: typed_from_runtime(v)
                    for k, v in {
                        FieldName("0", FieldKind.INDEX): 10,
                        FieldName("1", FieldKind.INDEX): 20,
                        FieldName("2", FieldKind.INDEX): 30,
                        FieldName("length", FieldKind.SPECIAL): 3,
                    }.items()
                }
            ),
        )
        ptr = Pointer(Address("arr_0"), 0)
        vm.current_frame.registers[Register("%ptr")] = typed_from_runtime(ptr)
        vm.current_frame.registers[Register("%1")] = typed_from_runtime(1)

        # ptr + 1
        add_inst = _make_inst(
            Opcode.BINOP, result_reg="%ptr1", operands=["+", "%ptr", "%1"]
        )
        add_result = _handle_binop(add_inst, vm, _CTX)
        _apply(vm, add_result)

        # *(ptr + 1)
        deref_inst = _make_inst(
            Opcode.LOAD_INDIRECT, result_reg="%val", operands=["%ptr1"]
        )
        deref_result = _handle_load_indirect(deref_inst, vm, _CTX)
        _apply(vm, deref_result)

        assert unwrap(vm.current_frame.registers[Register("%val")]) == 20


# ── Pointer subtraction and comparison ────────────────────────────


class TestPointerSubtraction:
    def test_pointer_minus_pointer_same_base(self):
        """Pointer - Pointer with same base should return offset difference."""
        vm = _make_vm()
        vm.current_frame.registers[Register("%p1")] = Pointer(Address("arr_0"), 1)
        vm.current_frame.registers[Register("%p2")] = Pointer(Address("arr_0"), 4)

        inst = _make_inst(
            Opcode.BINOP, result_reg="%diff", operands=["-", "%p2", "%p1"]
        )
        result = _handle_binop(inst, vm, _CTX)
        _apply(vm, result)

        assert unwrap(vm.current_frame.registers[Register("%diff")]) == 3

    def test_pointer_minus_pointer_negative(self):
        """Lower pointer minus higher pointer should give negative difference."""
        vm = _make_vm()
        vm.current_frame.registers[Register("%p1")] = Pointer(Address("arr_0"), 5)
        vm.current_frame.registers[Register("%p2")] = Pointer(Address("arr_0"), 2)

        inst = _make_inst(
            Opcode.BINOP, result_reg="%diff", operands=["-", "%p2", "%p1"]
        )
        result = _handle_binop(inst, vm, _CTX)
        _apply(vm, result)

        assert unwrap(vm.current_frame.registers[Register("%diff")]) == -3


class TestPointerComparison:
    def test_less_than(self):
        """Pointer < Pointer should compare offsets."""
        vm = _make_vm()
        vm.current_frame.registers[Register("%p1")] = Pointer(Address("arr_0"), 0)
        vm.current_frame.registers[Register("%p2")] = Pointer(Address("arr_0"), 1)

        inst = _make_inst(Opcode.BINOP, result_reg="%r", operands=["<", "%p1", "%p2"])
        result = _handle_binop(inst, vm, _CTX)
        _apply(vm, result)

        assert unwrap(vm.current_frame.registers[Register("%r")]) is True

    def test_greater_than(self):
        """Pointer > Pointer should compare offsets."""
        vm = _make_vm()
        vm.current_frame.registers[Register("%p1")] = Pointer(Address("arr_0"), 3)
        vm.current_frame.registers[Register("%p2")] = Pointer(Address("arr_0"), 1)

        inst = _make_inst(Opcode.BINOP, result_reg="%r", operands=[">", "%p1", "%p2"])
        result = _handle_binop(inst, vm, _CTX)
        _apply(vm, result)

        assert unwrap(vm.current_frame.registers[Register("%r")]) is True

    def test_less_than_or_equal(self):
        """Pointer <= Pointer with equal offsets should be True."""
        vm = _make_vm()
        vm.current_frame.registers[Register("%p1")] = Pointer(Address("arr_0"), 2)
        vm.current_frame.registers[Register("%p2")] = Pointer(Address("arr_0"), 2)

        inst = _make_inst(Opcode.BINOP, result_reg="%r", operands=["<=", "%p1", "%p2"])
        result = _handle_binop(inst, vm, _CTX)
        _apply(vm, result)

        assert unwrap(vm.current_frame.registers[Register("%r")]) is True

    def test_not_equal(self):
        """Pointer != Pointer with different offsets should be True."""
        vm = _make_vm()
        vm.current_frame.registers[Register("%p1")] = Pointer(Address("arr_0"), 0)
        vm.current_frame.registers[Register("%p2")] = Pointer(Address("arr_0"), 3)

        inst = _make_inst(Opcode.BINOP, result_reg="%r", operands=["!=", "%p1", "%p2"])
        result = _handle_binop(inst, vm, _CTX)
        _apply(vm, result)

        assert unwrap(vm.current_frame.registers[Register("%r")]) is True


# ── Nested pointers ──────────────────────────────────────────────


class TestNestedPointers:
    def test_double_pointer(self):
        """int **pp = &ptr where ptr = &x: **pp should reach x's value."""
        vm = _make_vm(x=42)

        # ptr = &x
        inst1 = _make_inst(Opcode.ADDRESS_OF, result_reg="%ptr", operands=["x"])
        _apply(vm, _handle_address_of(inst1, vm, _CTX))
        # Store ptr as a local variable (keep as TypedValue)
        vm.current_frame.local_vars[VarName("ptr")] = vm.current_frame.registers[
            Register("%ptr")
        ]

        # pp = &ptr
        inst2 = _make_inst(Opcode.ADDRESS_OF, result_reg="%pp", operands=["ptr"])
        _apply(vm, _handle_address_of(inst2, vm, _CTX))
        pp = unwrap(vm.current_frame.registers[Register("%pp")])

        # *pp should give us the Pointer to x
        deref1 = _make_inst(Opcode.LOAD_INDIRECT, result_reg="%inner", operands=["%pp"])
        _apply(vm, _handle_load_indirect(deref1, vm, _CTX))
        inner = unwrap(vm.current_frame.registers[Register("%inner")])
        assert isinstance(inner, Pointer)

        # **pp should give us 42
        deref2 = _make_inst(
            Opcode.LOAD_INDIRECT, result_reg="%val", operands=["%inner"]
        )
        _apply(vm, _handle_load_indirect(deref2, vm, _CTX))
        assert unwrap(vm.current_frame.registers[Register("%val")]) == 42
