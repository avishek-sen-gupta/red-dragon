"""Unit tests for DECL_VAR vs STORE_VAR scope chain semantics.

DECL_VAR always creates/overwrites in the current frame (declaration).
STORE_VAR walks the scope chain to update existing variables (assignment).
"""

from interpreter.ir import IRInstruction, Opcode
from interpreter.typed_value import typed_from_runtime, unwrap
from interpreter.vm import VMState, apply_update
from interpreter.vm_types import StackFrame, StateUpdate, StackFramePush
from interpreter.executor import LocalExecutor
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry


def _make_vm() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


def _execute(vm, inst):
    result = LocalExecutor.execute(
        inst=inst, vm=vm, cfg=CFG(), registry=FunctionRegistry()
    )
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
        assert unwrap(vm.current_frame.local_vars["x"]) == 42

    def test_shadows_parent_frame_variable(self):
        """DECL_VAR in inner frame should NOT modify parent frame."""
        vm = _make_vm()
        _set_reg(vm, "%v1", 10)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v1"]))

        _push_frame(vm)
        _set_reg(vm, "%v2", 99)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v2"]))

        # Inner frame has 99
        assert unwrap(vm.current_frame.local_vars["x"]) == 99
        # Parent frame still has 10
        assert unwrap(vm.call_stack[0].local_vars["x"]) == 10


class TestStoreVarScopeChain:
    """STORE_VAR walks the scope chain for existing variables."""

    def test_creates_local_when_not_in_parent(self):
        """STORE_VAR for a new variable creates in current frame."""
        vm = _make_vm()
        _set_reg(vm, "%v", 42)
        _execute(vm, IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "%v"]))
        assert unwrap(vm.current_frame.local_vars["x"]) == 42

    def test_updates_parent_frame_variable(self):
        """STORE_VAR should update variable in parent frame when it exists there."""
        vm = _make_vm()
        _set_reg(vm, "%v1", 10)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v1"]))

        _push_frame(vm)
        _set_reg(vm, "%v2", 42)
        _execute(vm, IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "%v2"]))

        # Parent frame updated to 42
        assert unwrap(vm.call_stack[0].local_vars["x"]) == 42
        # Inner frame should NOT have x (it updated the parent, not created local)
        assert "x" not in vm.current_frame.local_vars

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
        assert unwrap(vm.call_stack[0].local_vars["x"]) == 99
        # Middle and inner frames don't have x
        assert "x" not in vm.call_stack[1].local_vars
        assert "x" not in vm.call_stack[2].local_vars

    def test_decl_then_store_in_same_frame(self):
        """DECL_VAR then STORE_VAR in same frame updates same frame."""
        vm = _make_vm()
        _set_reg(vm, "%v1", 10)
        _execute(vm, IRInstruction(opcode=Opcode.DECL_VAR, operands=["x", "%v1"]))
        _set_reg(vm, "%v2", 20)
        _execute(vm, IRInstruction(opcode=Opcode.STORE_VAR, operands=["x", "%v2"]))
        assert unwrap(vm.current_frame.local_vars["x"]) == 20

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
        assert unwrap(vm.current_frame.local_vars["x"]) == 30
        # Parent frame x unchanged
        assert unwrap(vm.call_stack[0].local_vars["x"]) == 10
