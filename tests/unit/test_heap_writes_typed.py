"""Unit tests for heap_writes TypedValue migration (red-dragon-gny + red-dragon-x2t)."""

from types import MappingProxyType

from interpreter.field_name import FieldName, FieldKind
from interpreter.var_name import VarName
from interpreter.constants import TypeName
from interpreter.types.coercion.identity_conversion_rules import IdentityConversionRules
from interpreter.ir import IRInstruction, Opcode
from interpreter.vm.executor import (
    _handle_store_field,
    _handle_store_indirect,
    _handle_store_index,
    _handle_load_field,
    _handle_load_index,
    _handle_load_var,
    _handle_address_of,
    _default_handler_context,
)
from interpreter.types.type_environment import TypeEnvironment
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.vm.vm import apply_update, materialize_raw_update
from interpreter.register import Register
from interpreter.address import Address
from interpreter.func_name import FuncName
from interpreter.vm.vm_types import (
    HeapObject,
    HeapWrite,
    Pointer,
    StackFrame,
    StateUpdate,
    SymbolicValue,
    VMState,
)

_EMPTY_TYPE_ENV = TypeEnvironment(
    register_types=MappingProxyType({}),
    var_types=MappingProxyType({}),
)
_IDENTITY_RULES = IdentityConversionRules()
_CTX = _default_handler_context()


class TestStoreFieldTypedValue:
    """Tests for _handle_store_field producing TypedValue in HeapWrite.value."""

    def test_store_field_produces_typed_value(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.heap_set(Address("obj_0"), HeapObject(type_hint=scalar("Point")))
        vm.current_frame.registers[Register("%0")] = typed("obj_0", UNKNOWN)
        vm.current_frame.registers[Register("%1")] = typed(42, scalar(TypeName.INT))
        inst = IRInstruction(opcode=Opcode.STORE_FIELD, operands=["%0", "x", "%1"])
        result = _handle_store_field(inst, vm, _CTX)
        hw = result.update.heap_writes[0]
        assert isinstance(hw.value, TypedValue)
        assert hw.value.value == 42

    def test_store_indirect_pointer_dereference_produces_typed_value(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.heap_set(
            Address("mem_0"), HeapObject(fields={FieldName("0", FieldKind.INDEX): 0})
        )
        vm.current_frame.registers[Register("%0")] = typed(
            Pointer(base=Address("mem_0"), offset=0), UNKNOWN
        )
        vm.current_frame.registers[Register("%1")] = typed(99, scalar(TypeName.INT))
        inst = IRInstruction(opcode=Opcode.STORE_INDIRECT, operands=["%0", "%1"])
        result = _handle_store_indirect(inst, vm, _CTX)
        hw = result.update.heap_writes[0]
        assert isinstance(hw.value, TypedValue)
        assert hw.value.value == 99

    def test_store_field_string_value(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.heap_set(Address("obj_0"), HeapObject(type_hint=scalar("Person")))
        vm.current_frame.registers[Register("%0")] = typed("obj_0", UNKNOWN)
        vm.current_frame.registers[Register("%1")] = typed(
            "Alice", scalar(TypeName.STRING)
        )
        inst = IRInstruction(opcode=Opcode.STORE_FIELD, operands=["%0", "name", "%1"])
        result = _handle_store_field(inst, vm, _CTX)
        hw = result.update.heap_writes[0]
        assert isinstance(hw.value, TypedValue)
        assert hw.value.value == "Alice"


class TestStoreIndexTypedValue:
    """Tests for _handle_store_index producing TypedValue in HeapWrite.value."""

    def test_store_index_produces_typed_value(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.heap_set(
            Address("arr_0"),
            HeapObject(
                type_hint=scalar("array"),
                fields={FieldName("length", FieldKind.SPECIAL): 3},
            ),
        )
        vm.current_frame.registers[Register("%0")] = typed("arr_0", UNKNOWN)
        vm.current_frame.registers[Register("%1")] = typed(0, scalar(TypeName.INT))
        vm.current_frame.registers[Register("%2")] = typed(100, scalar(TypeName.INT))
        inst = IRInstruction(
            opcode=Opcode.STORE_INDEX,
            operands=["%0", "%1", "%2"],
            result_reg=Register("%3"),
        )
        result = _handle_store_index(inst, vm, _CTX)
        hw = result.update.heap_writes[0]
        assert isinstance(hw.value, TypedValue)
        assert hw.value.value == 100


class TestMaterializeHeapWrites:
    """Tests for materialize_raw_update handling heap_writes."""

    def test_raw_int_heap_write_materialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(
            heap_writes=[
                HeapWrite(obj_addr=Address("obj_0"), field=FieldName("x"), value=42)
            ],
            reasoning="test",
        )
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        hw = result.heap_writes[0]
        assert isinstance(hw.value, TypedValue)
        assert hw.value.value == 42
        assert hw.value.type == scalar(TypeName.INT)

    def test_symbolic_dict_heap_write_materialized(self):

        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        sym_dict = {"__symbolic__": True, "name": "sym_0", "type_hint": "Int"}
        raw = StateUpdate(
            heap_writes=[
                HeapWrite(
                    obj_addr=Address("obj_0"), field=FieldName("x"), value=sym_dict
                )
            ],
            reasoning="test",
        )
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        hw = result.heap_writes[0]
        assert isinstance(hw.value, TypedValue)
        assert isinstance(hw.value.value, SymbolicValue)
        assert hw.value.value.name == "sym_0"

    def test_already_typed_heap_write_passes_through(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        tv = typed(42, scalar(TypeName.INT))
        raw = StateUpdate(
            heap_writes=[
                HeapWrite(obj_addr=Address("obj_0"), field=FieldName("x"), value=tv)
            ],
            reasoning="test",
        )
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert result.heap_writes[0].value is tv

    def test_empty_heap_writes_unchanged(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert result.heap_writes == []


class TestApplyUpdateStoresTypedValue:
    """Phase 2: apply_update stores TypedValue directly in HeapObject.fields."""

    def test_apply_update_stores_typed_value_in_heap(self):
        """apply_update should store TypedValue directly in HeapObject.fields."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.heap_set(Address("obj_0"), HeapObject(type_hint=scalar("Point")))
        tv = typed(42, scalar(TypeName.INT))
        update = StateUpdate(
            heap_writes=[
                HeapWrite(obj_addr=Address("obj_0"), field=FieldName("x"), value=tv)
            ],
            reasoning="test",
        )
        apply_update(vm, update, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        field_val = vm.heap_get(Address("obj_0")).fields[FieldName("x")]
        assert isinstance(field_val, TypedValue)
        assert field_val.value == 42
        assert field_val.type == scalar(TypeName.INT)

    def test_alias_var_write_stores_typed_value_in_heap(self):
        """Alias var_write should store TypedValue in HeapObject.fields."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.heap_set(
            Address("mem_0"),
            HeapObject(
                type_hint=None,
                fields={FieldName("0", FieldKind.INDEX): typed_from_runtime(0)},
            ),
        )
        ptr = Pointer(base=Address("mem_0"), offset=0)
        vm.current_frame.var_heap_aliases[VarName("x")] = ptr
        tv = typed(99, scalar(TypeName.INT))
        update = StateUpdate(var_writes={VarName("x"): tv}, reasoning="test")
        apply_update(vm, update, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        field_val = vm.heap_get(Address("mem_0")).fields[
            FieldName("0", FieldKind.INDEX)
        ]
        assert isinstance(field_val, TypedValue)
        assert field_val.value == 99


class TestHeapFieldsStoreTypedValue:
    """Phase 2: HeapObject.fields stores TypedValue; readers pass through."""

    def test_symbolic_cache_stores_typed_value(self):
        """_handle_load_field symbolic cache stores typed(sym, UNKNOWN) in fields."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.heap_set(Address("obj_0"), HeapObject(type_hint=scalar("Foo")))
        vm.current_frame.registers[Register("%0")] = typed("obj_0", UNKNOWN)
        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD, operands=["%0", "bar"], result_reg=Register("%1")
        )
        _handle_load_field(inst, vm, _CTX)
        field_val = vm.heap_get(Address("obj_0")).fields[FieldName("bar")]
        assert isinstance(field_val, TypedValue)

    def test_address_of_stores_typed_value(self):
        """_handle_address_of stores TypedValue in promoted heap object."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.current_frame.local_vars[VarName("x")] = typed(42, scalar(TypeName.INT))
        inst = IRInstruction(
            opcode=Opcode.ADDRESS_OF, operands=["x"], result_reg=Register("%0")
        )
        _handle_address_of(inst, vm, _CTX)
        heap_objs = [
            obj
            for obj in vm.heap_values()
            if obj.fields.get(FieldName("0", FieldKind.INDEX)) is not None
        ]
        assert len(heap_objs) == 1
        field_val = heap_objs[0].fields[FieldName("0", FieldKind.INDEX)]
        assert isinstance(field_val, TypedValue)
        assert field_val.value == 42

    def test_load_field_passes_through_typed_value(self):
        """_handle_load_field passes through TypedValue from heap without re-wrapping."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        original_tv = typed(42, scalar(TypeName.INT))
        vm.heap_set(
            Address("obj_0"),
            HeapObject(type_hint=scalar("Point"), fields={FieldName("x"): original_tv}),
        )
        vm.current_frame.registers[Register("%0")] = typed("obj_0", UNKNOWN)
        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD, operands=["%0", "x"], result_reg=Register("%1")
        )
        result = _handle_load_field(inst, vm, _CTX)
        loaded_tv = result.update.register_writes[Register("%1")]
        assert loaded_tv is original_tv

    def test_load_index_passes_through_typed_value(self):
        """_handle_load_index passes through TypedValue from heap."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        original_tv = typed(99, scalar(TypeName.INT))
        vm.heap_set(
            Address("arr_0"),
            HeapObject(
                type_hint="array",
                fields={
                    FieldName("0", FieldKind.INDEX): original_tv,
                    FieldName("length", FieldKind.SPECIAL): typed(
                        1, scalar(TypeName.INT)
                    ),
                },
            ),
        )
        vm.current_frame.registers[Register("%0")] = typed("arr_0", UNKNOWN)
        vm.current_frame.registers[Register("%1")] = typed(0, scalar(TypeName.INT))
        inst = IRInstruction(
            opcode=Opcode.LOAD_INDEX, operands=["%0", "%1"], result_reg=Register("%2")
        )
        result = _handle_load_index(inst, vm, _CTX)
        loaded_tv = result.update.register_writes[Register("%2")]
        assert loaded_tv is original_tv

    def test_load_var_alias_passes_through_typed_value(self):
        """_handle_load_var alias path passes through TypedValue from heap."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        original_tv = typed(77, scalar(TypeName.INT))
        vm.heap_set(
            Address("mem_0"),
            HeapObject(fields={FieldName("0", FieldKind.INDEX): original_tv}),
        )
        ptr = Pointer(base=Address("mem_0"), offset=0)
        vm.current_frame.var_heap_aliases[VarName("x")] = ptr
        inst = IRInstruction(
            opcode=Opcode.LOAD_VAR, operands=["x"], result_reg=Register("%0")
        )
        result = _handle_load_var(inst, vm, _CTX)
        loaded_tv = result.update.register_writes[Register("%0")]
        assert loaded_tv is original_tv
