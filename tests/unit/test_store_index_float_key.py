"""Tests proving the float-index heap key mismatch bug is fixed.

When STORE_INDEX receives a float index (e.g. 2.0) and the type environment
declares that register as Int, apply_update coerces the float to int at
write time — so str(2) == "2" matches on both store and load.
"""

from types import MappingProxyType

from interpreter.types.typed_value import TypedValue, typed_from_runtime, unwrap

from interpreter.types.coercion.default_conversion_rules import (
    DefaultTypeConversionRules,
)
from interpreter.types.function_signature import FunctionSignature
from interpreter.ir import IRInstruction, Opcode
from interpreter.types.type_environment import TypeEnvironment
from interpreter.vm.vm import VMState, apply_update, _heap_addr
from interpreter.vm.vm_types import StackFrame, StateUpdate
from interpreter.vm.executor import (
    LocalExecutor,
    HandlerContext,
    _default_handler_context,
)
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry


def _make_vm() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


def _empty_cfg() -> CFG:
    return CFG()


def _empty_registry() -> FunctionRegistry:
    return FunctionRegistry()


def _type_env_with(register_types: dict[str, str]) -> TypeEnvironment:
    return TypeEnvironment(
        register_types=MappingProxyType(register_types),
        var_types=MappingProxyType({}),
    )


def _set_reg(vm, reg, val, type_env=None, conversion_rules=None):
    """Write a value to a register through apply_update so coercion fires."""
    kwargs = {}
    if type_env is not None:
        kwargs["type_env"] = type_env
    if conversion_rules is not None:
        kwargs["conversion_rules"] = conversion_rules
    tv = val if isinstance(val, TypedValue) else typed_from_runtime(val)
    apply_update(vm, StateUpdate(register_writes={reg: tv}), **kwargs)


def _execute(vm, inst, type_env=None, conversion_rules=None):
    result = LocalExecutor.execute(
        inst=inst,
        vm=vm,
        ctx=_default_handler_context(),
    )
    assert result.handled
    kwargs = {}
    if type_env is not None:
        kwargs["type_env"] = type_env
    if conversion_rules is not None:
        kwargs["conversion_rules"] = conversion_rules
    apply_update(vm, result.update, **kwargs)
    return result


def _setup_array(vm):
    """Create a NEW_ARRAY on the heap and return the vm with %arr set."""
    _execute(
        vm,
        IRInstruction(
            opcode=Opcode.NEW_ARRAY,
            result_reg="%arr",
            operands=["int"],
        ),
    )
    return vm


class TestFloatIndexHeapKeyMismatch:
    def test_float_store_int_load_reads_back_stored_value(self):
        """STORE_INDEX with float 2.0, then LOAD_INDEX with int 2 — value should round-trip."""
        vm = _setup_array(_make_vm())
        type_env = _type_env_with({"%idx_f": "Int"})
        rules = DefaultTypeConversionRules()

        # Store value 42 at float index 2.0 (coerced to int 2 at write time)
        _set_reg(vm, "%idx_f", 2.0, type_env=type_env, conversion_rules=rules)
        _set_reg(vm, "%val", 42)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.STORE_INDEX,
                operands=["%arr", "%idx_f", "%val"],
            ),
            type_env=type_env,
            conversion_rules=rules,
        )

        # Load from int index 2
        _set_reg(vm, "%idx_i", 2)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_INDEX,
                result_reg="%out",
                operands=["%arr", "%idx_i"],
            ),
            type_env=type_env,
            conversion_rules=rules,
        )

        assert unwrap(vm.current_frame.registers["%out"]) == 42

    def test_int_store_float_load_reads_back_stored_value(self):
        """STORE_INDEX with int 2, then LOAD_INDEX with float 2.0 — value should round-trip."""
        vm = _setup_array(_make_vm())
        type_env = _type_env_with({"%idx_i": "Int", "%idx_f": "Int"})
        rules = DefaultTypeConversionRules()

        # Store value 99 at int index 2
        _set_reg(vm, "%idx_i", 2)
        _set_reg(vm, "%val", 99)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.STORE_INDEX,
                operands=["%arr", "%idx_i", "%val"],
            ),
            type_env=type_env,
            conversion_rules=rules,
        )

        # Load from float index 2.0 (coerced to int 2 at write time)
        _set_reg(vm, "%idx_f", 2.0, type_env=type_env, conversion_rules=rules)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.LOAD_INDEX,
                result_reg="%out",
                operands=["%arr", "%idx_f"],
            ),
            type_env=type_env,
            conversion_rules=rules,
        )

        assert unwrap(vm.current_frame.registers["%out"]) == 99

    def test_heap_key_written_by_float_index_with_type_coercion(self):
        """After STORE_INDEX with float 2.0 and type env saying Int, heap key is '2' not '2.0'."""
        vm = _setup_array(_make_vm())
        type_env = _type_env_with({"%idx_f": "Int"})
        rules = DefaultTypeConversionRules()

        _set_reg(vm, "%idx_f", 2.0, type_env=type_env, conversion_rules=rules)
        _set_reg(vm, "%val", 77)
        _execute(
            vm,
            IRInstruction(
                opcode=Opcode.STORE_INDEX,
                operands=["%arr", "%idx_f", "%val"],
            ),
            type_env=type_env,
            conversion_rules=rules,
        )

        arr_addr = _heap_addr(unwrap(vm.current_frame.registers["%arr"]))
        heap_obj = vm.heap[arr_addr]
        assert "2" in heap_obj.fields, "Expected int key '2' in heap fields"
        assert (
            "2.0" not in heap_obj.fields
        ), "Key '2.0' should NOT exist — float was coerced to int"
