"""Unit tests for DECL_VAR vs STORE_VAR scope chain semantics.

DECL_VAR always creates/overwrites in the current frame (declaration).
STORE_VAR walks the scope chain to update existing variables (assignment).
"""

from interpreter.address import Address
from interpreter.field_name import FieldName
from interpreter.var_name import VarName
from interpreter.ir import IRInstruction, Opcode
from interpreter.types.typed_value import typed_from_runtime, unwrap, typed
from interpreter.vm.vm import VMState, apply_update
from interpreter.vm.vm_types import HeapObject, StackFrame, StateUpdate, StackFramePush
from interpreter.types.type_expr import UNKNOWN
from interpreter.vm.field_fallback import ImplicitThisFieldFallback
from interpreter.vm.executor import (
    LocalExecutor,
    HandlerContext,
    _default_handler_context,
)
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry
from interpreter.register import Register


def _make_vm() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


def _execute(vm, inst, **kwargs):
    from dataclasses import replace

    ctx = _default_handler_context()
    if kwargs:
        ctx = replace(ctx, **kwargs)
    result = LocalExecutor.execute(inst=inst, vm=vm, ctx=ctx)
    assert result.handled
    apply_update(vm, result.update)
    return result


def _set_reg(vm, reg, val):
    apply_update(vm, StateUpdate(register_writes={reg: typed_from_runtime(val)}))


def _push_frame(vm, name="inner"):
    vm.call_stack.append(StackFrame(function_name=name))


class TestDeclVar:
    """DECL_VAR always writes to the current frame."""

    def test_creates_in_current_frame(self):
        vm = _make_vm()
        _set_reg(vm, "%v", 42)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v"]))
        assert unwrap(vm.current_frame.local_vars[VarName("x")]) == 42

    def test_shadows_parent_frame_variable(self):
        """DECL_VAR in inner frame should NOT modify parent frame."""
        vm = _make_vm()
        _set_reg(vm, "%v1", 10)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v1"]))

        _push_frame(vm)
        _set_reg(vm, "%v2", 99)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v2"]))

        # Inner frame has 99
        assert unwrap(vm.current_frame.local_vars[VarName("x")]) == 99
        # Parent frame still has 10
        assert unwrap(vm.call_stack[0].local_vars[VarName("x")]) == 10


class TestStoreVarScopeChain:
    """STORE_VAR walks the scope chain for existing variables."""

    def test_creates_local_when_not_in_parent(self):
        """STORE_VAR for a new variable creates in current frame."""
        vm = _make_vm()
        _set_reg(vm, "%v", 42)
        _execute(vm, IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "%v"]))
        assert unwrap(vm.current_frame.local_vars[VarName("x")]) == 42

    def test_updates_parent_frame_variable(self):
        """STORE_VAR should update variable in parent frame when it exists there."""
        vm = _make_vm()
        _set_reg(vm, "%v1", 10)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v1"]))

        _push_frame(vm)
        _set_reg(vm, "%v2", 42)
        _execute(vm, IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "%v2"]))

        # Parent frame updated to 42
        assert unwrap(vm.call_stack[0].local_vars[VarName("x")]) == 42
        # Inner frame should NOT have x (it updated the parent, not created local)
        assert VarName("x") not in vm.current_frame.local_vars

    def test_updates_grandparent_frame(self):
        """STORE_VAR should walk past intermediate frames."""
        vm = _make_vm()
        _set_reg(vm, "%v1", 10)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v1"]))

        _push_frame(vm, "middle")
        _push_frame(vm, "inner")
        _set_reg(vm, "%v2", 99)
        _execute(vm, IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "%v2"]))

        # Grandparent (main) frame updated
        assert unwrap(vm.call_stack[0].local_vars[VarName("x")]) == 99
        # Middle and inner frames don't have x
        assert VarName("x") not in vm.call_stack[1].local_vars
        assert VarName("x") not in vm.call_stack[2].local_vars

    def test_decl_then_store_in_same_frame(self):
        """DECL_VAR then STORE_VAR in same frame updates same frame."""
        vm = _make_vm()
        _set_reg(vm, "%v1", 10)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v1"]))
        _set_reg(vm, "%v2", 20)
        _execute(vm, IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "%v2"]))
        assert unwrap(vm.current_frame.local_vars[VarName("x")]) == 20

    def test_inner_decl_shadows_then_store_updates_inner(self):
        """If inner frame declares x (DECL_VAR), STORE_VAR in inner frame updates inner x."""
        vm = _make_vm()
        _set_reg(vm, "%v1", 10)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v1"]))

        _push_frame(vm)
        _set_reg(vm, "%v2", 20)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v2"]))
        _set_reg(vm, "%v3", 30)
        _execute(vm, IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "%v3"]))

        # Inner frame x updated to 30
        assert unwrap(vm.current_frame.local_vars[VarName("x")]) == 30
        # Parent frame x unchanged
        assert unwrap(vm.call_stack[0].local_vars[VarName("x")]) == 10


class TestImplicitThisFieldResolution:
    """LOAD_VAR falls back to this.field when ImplicitThisFieldFallback is injected."""

    FALLBACK = ImplicitThisFieldFallback()

    def _make_vm_with_this(self, fields: dict) -> VMState:
        """Create a VM with a heap object and 'this' pointing to it."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="<main>"))
        addr = Address("obj_0")
        heap_fields = {FieldName(k): typed(v, UNKNOWN) for k, v in fields.items()}
        vm.heap_set(addr, HeapObject(fields=heap_fields))
        vm.current_frame.local_vars[VarName("this")] = typed(addr, UNKNOWN)
        return vm

    def test_bare_field_resolves_via_this(self):
        """LOAD_VAR 'count' should find this.count when count not in scope."""
        vm = self._make_vm_with_this({"count": 42})
        _execute(
            vm,
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%0", operands=["count"]),
            field_fallback=self.FALLBACK,
        )
        assert unwrap(vm.current_frame.registers[Register("%0")]) == 42

    def test_local_var_takes_precedence_over_field(self):
        """Local variable should shadow this.field."""
        vm = self._make_vm_with_this({"x": 10})
        _set_reg(vm, "%v", 99)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v"]))
        _execute(
            vm,
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%0", operands=["x"]),
            field_fallback=self.FALLBACK,
        )
        assert unwrap(vm.current_frame.registers[Register("%0")]) == 99

    def test_no_this_produces_symbolic(self):
        """Without this in scope, missing var should still produce symbolic."""
        vm = _make_vm()
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_VAR, result_reg="%0", operands=["missing"]
            ),
            field_fallback=self.FALLBACK,
        )
        val = vm.current_frame.registers[Register("%0")].value
        assert hasattr(val, "name"), f"Expected symbolic, got {val}"

    def test_field_not_on_heap_object_produces_symbolic(self):
        """this exists but field not on object should produce symbolic."""
        vm = self._make_vm_with_this({"other": 5})
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_VAR, result_reg="%0", operands=["missing"]
            ),
            field_fallback=self.FALLBACK,
        )
        val = vm.current_frame.registers[Register("%0")].value
        assert hasattr(val, "name"), f"Expected symbolic, got {val}"

    def test_no_fallback_strategy_produces_symbolic(self):
        """Without ImplicitThisFieldFallback, bare field name produces symbolic."""
        vm = self._make_vm_with_this({"count": 42})
        _execute(
            vm,
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%0", operands=["count"]),
            # No field_fallback — uses default NoFieldFallback
        )
        val = vm.current_frame.registers[Register("%0")].value
        assert hasattr(val, "name"), f"Expected symbolic without fallback, got {val}"

    def test_store_var_writes_to_this_field(self):
        """STORE_VAR should write to this.field when var not in scope."""
        vm = self._make_vm_with_this({"doubled": 0})
        _set_reg(vm, "%v", 42)
        _execute(
            vm,
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["doubled", "%v"]),
            field_fallback=self.FALLBACK,
        )
        assert unwrap(vm.heap_get(Address("obj_0")).fields[FieldName("doubled")]) == 42
