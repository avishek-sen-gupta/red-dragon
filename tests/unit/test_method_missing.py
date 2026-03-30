"""Tests for __method_missing__ fallback in LOAD_FIELD handler.

When a heap object has a __method_missing__ field (a BoundFuncRef), loading a
non-existent field should dispatch through that function instead of returning
a symbolic value.
"""

from interpreter.address import Address
from interpreter.class_name import ClassName
from interpreter.field_name import FieldName, FieldKind
from interpreter.func_name import FuncName
from interpreter.cfg import CFG
from interpreter.cfg_types import BasicBlock
from interpreter.constants import BOXED_FIELD, METHOD_MISSING
from interpreter.vm.executor import (
    LocalExecutor,
    HandlerContext,
    _default_handler_context,
)
from interpreter.refs.func_ref import BoundFuncRef, FuncRef
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.registry import FunctionRegistry
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime, unwrap
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.vm.vm import HeapObject, VMState
from interpreter.vm.vm_types import StackFrame, StateUpdate, SymbolicValue
from interpreter.register import Register


from dataclasses import replace as _replace


def _ctx(**overrides) -> HandlerContext:
    return _replace(_default_handler_context(), **overrides)


def _make_vm_with_method_missing(
    inner_fields: dict[str, TypedValue],
) -> tuple[VMState, CFG, FunctionRegistry]:
    """Create VM with outer object that has __method_missing__ delegating to inner."""
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=FuncName("<test>")))

    # Inner object
    inner_addr = Address("obj_0")
    vm.heap_set(inner_addr, HeapObject(type_hint="Inner", fields=inner_fields))

    # __method_missing__ function: takes (self, name) -> LOAD_FIELD_INDIRECT(self.BOXED_FIELD, name)
    mm_label = CodeLabel("func_mm_0")
    cfg = CFG()
    cfg.blocks[mm_label] = BasicBlock(
        label=mm_label,
        instructions=[
            IRInstruction(
                opcode=Opcode.LOAD_VAR,
                result_reg=Register("%mm_self"),
                operands=["self"],
            ),
            IRInstruction(
                opcode=Opcode.LOAD_FIELD,
                result_reg=Register("%mm_inner"),
                operands=["%mm_self", BOXED_FIELD],
            ),
            IRInstruction(
                opcode=Opcode.LOAD_VAR,
                result_reg=Register("%mm_name"),
                operands=["name"],
            ),
            IRInstruction(
                opcode=Opcode.LOAD_FIELD_INDIRECT,
                result_reg=Register("%mm_result"),
                operands=["%mm_inner", "%mm_name"],
            ),
            IRInstruction(opcode=Opcode.RETURN, operands=["%mm_result"]),
        ],
    )

    mm_func_ref = BoundFuncRef(
        func_ref=FuncRef(name=FuncName(METHOD_MISSING), label=mm_label)
    )

    # Outer object: BOXED_FIELD -> inner_addr, __method_missing__ -> func_ref
    outer_addr = Address("obj_1")
    vm.heap_set(
        outer_addr,
        HeapObject(
            type_hint="Outer",
            fields={
                FieldName(BOXED_FIELD): typed(inner_addr, scalar("Object")),
                FieldName(METHOD_MISSING): typed(mm_func_ref, UNKNOWN),
            },
        ),
    )
    vm.call_stack[-1].registers[Register("%outer")] = typed(
        outer_addr, scalar("Object")
    )

    registry = FunctionRegistry()
    registry.func_params[mm_label] = ["self", "name"]

    return vm, cfg, registry


class TestMethodMissingLoadField:
    def test_delegates_to_inner_object_field(self):
        """LOAD_FIELD for a missing field triggers __method_missing__ dispatch."""
        vm, cfg, registry = _make_vm_with_method_missing(
            inner_fields={FieldName("value"): typed_from_runtime(42)}
        )

        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD,
            result_reg=Register("%result"),
            operands=["%outer", "nonexistent_field"],
        )
        result = LocalExecutor.execute(
            inst=inst,
            vm=vm,
            ctx=_ctx(cfg=cfg, registry=registry),
        )

        assert result.handled
        assert result.update.call_push is not None
        assert result.update.next_label == "func_mm_0"

    def test_existing_field_does_not_trigger_method_missing(self):
        """LOAD_FIELD for BOXED_FIELD (which exists) returns directly, no method_missing."""
        vm, cfg, registry = _make_vm_with_method_missing(
            inner_fields={FieldName("value"): typed_from_runtime(42)}
        )

        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD,
            result_reg=Register("%result"),
            operands=["%outer", BOXED_FIELD],
        )
        result = LocalExecutor.execute(
            inst=inst,
            vm=vm,
            ctx=_ctx(cfg=cfg, registry=registry),
        )

        assert result.handled
        assert result.update.call_push is None
        assert unwrap(result.update.register_writes[Register("%result")]) == Address(
            "obj_0"
        )

    def test_no_method_missing_falls_through_to_symbolic(self):
        """Object WITHOUT __method_missing__; missing field returns SymbolicValue."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("<test>")))

        addr = Address("obj_0")
        vm.heap_set(
            addr,
            HeapObject(
                type_hint="Plain",
                fields={FieldName("x"): typed_from_runtime(10)},
            ),
        )
        vm.call_stack[-1].registers[Register("%obj")] = typed(addr, scalar("Object"))

        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD,
            result_reg=Register("%result"),
            operands=["%obj", "missing_field"],
        )
        result = LocalExecutor.execute(
            inst=inst,
            vm=vm,
            ctx=_default_handler_context(),
        )

        assert result.handled
        assert result.update.call_push is None
        assert isinstance(
            unwrap(result.update.register_writes[Register("%result")]), SymbolicValue
        )


class TestFindMethodMissingRegistryPath:
    """Tests that _find_method_missing finds __method_missing__ via registry.class_methods
    when it is NOT an instance field (the path used by Box prelude classes)."""

    def test_finds_method_missing_via_class_registry(self):
        """Object has no __method_missing__ field, but type has it in registry.class_methods."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("<test>")))

        addr = Address("obj_0")
        vm.heap_set(
            addr,
            HeapObject(
                type_hint="BoxType",
                fields={FieldName(BOXED_FIELD): typed("inner_0", scalar("Object"))},
            ),
        )
        vm.call_stack[-1].registers[Register("%obj")] = typed(addr, scalar("Object"))

        mm_label = CodeLabel("func_box_mm_0")
        cfg = CFG()
        cfg.blocks[mm_label] = BasicBlock(
            label=mm_label,
            instructions=[
                IRInstruction(opcode=Opcode.RETURN, operands=["%result"]),
            ],
        )
        registry = FunctionRegistry()
        registry.class_methods[ClassName("BoxType")] = {
            FuncName(METHOD_MISSING): [mm_label]
        }
        registry.func_params[mm_label] = ["self", "name"]

        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD,
            result_reg=Register("%result"),
            operands=["%obj", "some_field"],
        )
        result = LocalExecutor.execute(
            inst=inst,
            vm=vm,
            ctx=_ctx(cfg=cfg, registry=registry),
        )

        assert result.handled
        assert result.update.call_push is not None
        assert result.update.next_label == mm_label

    def test_instance_field_takes_precedence_over_registry(self):
        """If __method_missing__ exists as both instance field and registry entry,
        the instance field wins."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("<test>")))

        instance_mm_label = CodeLabel("func_instance_mm")
        registry_mm_label = CodeLabel("func_registry_mm")

        cfg = CFG()
        cfg.blocks[instance_mm_label] = BasicBlock(
            label=instance_mm_label,
            instructions=[IRInstruction(opcode=Opcode.RETURN, operands=["%r"])],
        )
        cfg.blocks[registry_mm_label] = BasicBlock(
            label=registry_mm_label,
            instructions=[IRInstruction(opcode=Opcode.RETURN, operands=["%r"])],
        )

        instance_mm_ref = BoundFuncRef(
            func_ref=FuncRef(name=FuncName(METHOD_MISSING), label=instance_mm_label),
        )

        addr = Address("obj_0")
        vm.heap_set(
            addr,
            HeapObject(
                type_hint="DualBox",
                fields={FieldName(METHOD_MISSING): typed(instance_mm_ref, UNKNOWN)},
            ),
        )
        vm.call_stack[-1].registers[Register("%obj")] = typed(addr, scalar("Object"))

        registry = FunctionRegistry()
        registry.class_methods[ClassName("DualBox")] = {
            FuncName(METHOD_MISSING): [registry_mm_label]
        }
        registry.func_params[instance_mm_label] = ["self", "name"]
        registry.func_params[registry_mm_label] = ["self", "name"]

        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD,
            result_reg=Register("%result"),
            operands=["%obj", "some_field"],
        )
        result = LocalExecutor.execute(
            inst=inst,
            vm=vm,
            ctx=_ctx(cfg=cfg, registry=registry),
        )

        assert result.handled
        assert result.update.call_push is not None
        assert result.update.next_label == instance_mm_label


class TestMethodMissingCallMethod:
    def test_delegates_method_call_to_inner_object_method(self):
        """CALL_METHOD for unknown method on Outer delegates to Inner's method via BOXED_FIELD."""
        vm, cfg, registry = _make_vm_with_method_missing(
            inner_fields={FieldName("value"): typed_from_runtime(42)}
        )
        # Register "Outer" with no methods, "Inner" with 'some_method'
        registry.class_methods[ClassName("Outer")] = {}
        inner_method_label = CodeLabel("func_inner_some_method_0")
        cfg.blocks[inner_method_label] = BasicBlock(
            label=inner_method_label,
            instructions=[
                IRInstruction(opcode=Opcode.RETURN, operands=["%result"]),
            ],
        )
        registry.class_methods[ClassName("Inner")] = {
            FuncName("some_method"): [inner_method_label]
        }
        registry.func_params[inner_method_label] = ["self", "arg"]

        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg=Register("%result"),
            operands=["%outer", "some_method", "%arg0"],
        )
        vm.call_stack[-1].registers[Register("%arg0")] = typed_from_runtime(99)

        result = LocalExecutor.execute(
            inst=inst,
            vm=vm,
            ctx=_ctx(cfg=cfg, registry=registry),
        )

        assert result.handled
        assert result.update.call_push is not None
        assert result.update.next_label == inner_method_label

    def test_unknown_method_on_inner_falls_through_to_symbolic(self):
        """CALL_METHOD for method not on Outer or Inner falls through to symbolic."""
        vm, cfg, registry = _make_vm_with_method_missing(
            inner_fields={FieldName("value"): typed_from_runtime(42)}
        )
        registry.class_methods[ClassName("Outer")] = {}

        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg=Register("%result"),
            operands=["%outer", "nonexistent_method", "%arg0"],
        )
        vm.call_stack[-1].registers[Register("%arg0")] = typed_from_runtime(99)

        result = LocalExecutor.execute(
            inst=inst,
            vm=vm,
            ctx=_ctx(cfg=cfg, registry=registry),
        )

        assert result.handled
        assert result.update.call_push is None
        assert isinstance(
            unwrap(result.update.register_writes[Register("%result")]), SymbolicValue
        )

    def test_existing_method_does_not_trigger_method_missing(self):
        """CALL_METHOD for known method dispatches to real label, not __method_missing__."""
        vm, cfg, registry = _make_vm_with_method_missing(
            inner_fields={FieldName("value"): typed_from_runtime(42)}
        )
        real_label = CodeLabel("func_real_method_0")
        cfg.blocks[real_label] = BasicBlock(
            label=real_label,
            instructions=[
                IRInstruction(opcode=Opcode.RETURN, operands=["%result"]),
            ],
        )
        registry.class_methods[ClassName("Outer")] = {
            FuncName("real_method"): [real_label]
        }
        registry.func_params[real_label] = ["self"]

        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg=Register("%result"),
            operands=["%outer", "real_method"],
        )

        result = LocalExecutor.execute(
            inst=inst,
            vm=vm,
            ctx=_ctx(cfg=cfg, registry=registry),
        )

        assert result.handled
        assert result.update.call_push is not None
        assert result.update.next_label == real_label
