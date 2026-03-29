"""Unit tests for CALL_FUNCTION array indexing (Scala apply semantics).

When CALL_FUNCTION targets a heap-backed array, the VM should resolve it
as array indexing. Out-of-bounds indices should produce symbolic values,
not crash by falling through to native string indexing.
"""

from interpreter.address import Address
from interpreter.field_name import FieldName, FieldKind
from interpreter.var_name import VarName
from interpreter.ir import IRInstruction, Opcode
from interpreter.types.typed_value import typed_from_runtime, unwrap
from interpreter.vm.vm import VMState, _is_symbolic, apply_update
from interpreter.vm.vm_types import HeapObject, StackFrame, StateUpdate
from interpreter.func_name import FuncName
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
    vm.call_stack.append(StackFrame(function_name=FuncName("<main>")))
    return vm


def _empty_cfg() -> CFG:
    return CFG()


def _empty_registry() -> FunctionRegistry:
    return FunctionRegistry()


def _set_reg(vm, reg, val):
    tv = val if isinstance(val, tuple) else typed_from_runtime(val)
    apply_update(vm, StateUpdate(register_writes={reg: tv}))


def _execute(vm, inst):
    result = LocalExecutor.execute(
        inst=inst,
        vm=vm,
        ctx=_default_handler_context(),
    )
    assert result.handled
    apply_update(vm, result.update)
    return result


def _setup_heap_array(vm, name, elements):
    """Create a heap-backed array and bind it to a local variable."""
    addr = Address(f"arr_{vm.symbolic_counter}")
    vm.symbolic_counter += 1
    fields = {
        FieldName(str(i), FieldKind.INDEX): typed_from_runtime(v)
        for i, v in enumerate(elements)
    }
    fields[FieldName("length", FieldKind.SPECIAL)] = typed_from_runtime(len(elements))
    vm.heap_set(addr, HeapObject(type_hint="array", fields=fields))
    vm.current_frame.local_vars[VarName(name)] = typed_from_runtime(addr)
    return addr


class TestCallFunctionHeapArrayIndexing:
    """CALL_FUNCTION on heap-backed arrays should resolve to indexing."""

    def test_valid_index_returns_element(self):
        """arr(0) on heap array [10, 20, 30] returns 10."""
        vm = _make_vm()
        _setup_heap_array(vm, "arr", [10, 20, 30])
        _set_reg(vm, "%idx", 0)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%out",
                operands=["arr", "%idx"],
            ),
        )
        assert unwrap(vm.current_frame.registers[Register("%out")]) == 10

    def test_last_index_returns_element(self):
        """arr(2) on heap array [10, 20, 30] returns 30."""
        vm = _make_vm()
        _setup_heap_array(vm, "arr", [10, 20, 30])
        _set_reg(vm, "%idx", 2)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%out",
                operands=["arr", "%idx"],
            ),
        )
        assert unwrap(vm.current_frame.registers[Register("%out")]) == 30

    def test_out_of_bounds_returns_symbolic(self):
        """arr(5) on heap array [10, 20, 30] should return symbolic, not crash."""
        vm = _make_vm()
        _setup_heap_array(vm, "arr", [10, 20, 30])
        _set_reg(vm, "%idx", 5)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%out",
                operands=["arr", "%idx"],
            ),
        )
        result = unwrap(vm.current_frame.registers[Register("%out")])
        assert _is_symbolic(
            result
        ), f"Expected symbolic for out-of-bounds, got {result!r}"

    def test_negative_index_returns_symbolic(self):
        """arr(-1) on heap array should return symbolic, not crash."""
        vm = _make_vm()
        _setup_heap_array(vm, "arr", [10, 20, 30])
        _set_reg(vm, "%idx", -1)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%out",
                operands=["arr", "%idx"],
            ),
        )
        result = unwrap(vm.current_frame.registers[Register("%out")])
        assert _is_symbolic(
            result
        ), f"Expected symbolic for negative index, got {result!r}"


class TestCallFunctionNativeStringIndexing:
    """CALL_FUNCTION on native strings should resolve to character indexing."""

    def test_string_index_returns_character(self):
        """s(1) on native string 'hello' returns 'e'."""
        vm = _make_vm()
        vm.current_frame.local_vars[VarName("s")] = typed_from_runtime("hello")
        _set_reg(vm, "%idx", 1)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%out",
                operands=["s", "%idx"],
            ),
        )
        assert unwrap(vm.current_frame.registers[Register("%out")]) == "e"
