"""Unit tests for materialize_raw_update."""

from types import MappingProxyType

from interpreter.address import Address
from interpreter.closure_id import ClosureId
from interpreter.field_name import FieldName, FieldKind
from interpreter.var_name import VarName
from interpreter.types.type_environment import TypeEnvironment
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.types.coercion.identity_conversion_rules import IdentityConversionRules
from interpreter.ir import CodeLabel
from interpreter.vm.vm import materialize_raw_update, apply_update
from interpreter.register import Register
from interpreter.func_name import FuncName
from interpreter.vm.vm_types import (
    StateUpdate,
    VMState,
    StackFrame,
    SymbolicValue,
    Pointer,
)

_EMPTY_TYPE_ENV = TypeEnvironment(
    register_types=MappingProxyType({}), var_types=MappingProxyType({})
)
_IDENTITY_RULES = IdentityConversionRules()


class TestMaterializeRawUpdate:
    def test_int_register_write(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(register_writes={Register("%0"): 42}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.register_writes[Register("%0")]
        assert isinstance(tv, TypedValue)
        assert tv.value == 42
        assert tv.type == scalar("Int")

    def test_string_register_write(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(register_writes={Register("%0"): "hello"}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.register_writes[Register("%0")]
        assert isinstance(tv, TypedValue)
        assert tv.value == "hello"
        assert tv.type == scalar("String")

    def test_symbolic_dict_deserialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        sym_dict = {
            "__symbolic__": True,
            "name": "sym_0",
            "type_hint": "Int",
            "constraints": [],
        }
        raw = StateUpdate(register_writes={Register("%0"): sym_dict}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.register_writes[Register("%0")]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, SymbolicValue)
        assert tv.value.name == "sym_0"

    def test_pointer_dict_deserialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        ptr_dict = {"__pointer__": True, "base": "mem_0", "offset": 4}
        raw = StateUpdate(register_writes={Register("%0"): ptr_dict}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.register_writes[Register("%0")]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert tv.value.base == Address("mem_0")
        assert tv.value.offset == 4

    def test_var_write_materialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(var_writes={VarName("x"): 10}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.var_writes[VarName("x")]
        assert isinstance(tv, TypedValue)
        assert tv.value == 10
        assert tv.type == scalar("Int")

    def test_non_register_var_fields_unchanged(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(
            register_writes={Register("%0"): 42},
            reasoning="test",
            next_label=CodeLabel("block_1"),
            path_condition="x > 0",
        )
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert result.next_label == "block_1"
        assert result.path_condition == "x > 0"
        assert result.reasoning == "test"

    def test_already_typed_value_passes_through(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        tv = typed(42, scalar("Int"))
        raw = StateUpdate(register_writes={Register("%0"): tv}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert result.register_writes[Register("%0")] is tv

    def test_register_coercion_applied(self):
        """Register values get coerced via _coerce_value during materialization."""
        from interpreter.types.coercion.default_conversion_rules import (
            DefaultTypeConversionRules,
        )

        type_env = TypeEnvironment(
            register_types=MappingProxyType({Register("%0"): scalar("Float")}),
            var_types=MappingProxyType({}),
        )
        rules = DefaultTypeConversionRules()
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(register_writes={Register("%0"): 42}, reasoning="test")
        result = materialize_raw_update(raw, vm, type_env, rules)
        tv = result.register_writes[Register("%0")]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, float)
        assert tv.type == scalar("Float")

    def test_var_write_no_coercion(self):
        """Var writes do NOT get register coercion (matching current behavior)."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(var_writes={VarName("x"): 42}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.var_writes[VarName("x")]
        assert tv.value == 42
        assert tv.type == scalar("Int")


class TestApplyUpdateTypedPath:
    def test_stores_typed_value_directly(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        tv = typed(42, scalar("Int"))
        update = StateUpdate(register_writes={Register("%0"): tv}, reasoning="test")
        apply_update(
            vm, update, type_env=_EMPTY_TYPE_ENV, conversion_rules=_IDENTITY_RULES
        )
        assert vm.current_frame.registers[Register("%0")] is tv

    def test_stores_typed_var_directly(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        tv = typed(10, scalar("Int"))
        update = StateUpdate(var_writes={VarName("x"): tv}, reasoning="test")
        apply_update(
            vm, update, type_env=_EMPTY_TYPE_ENV, conversion_rules=_IDENTITY_RULES
        )
        assert vm.current_frame.local_vars[VarName("x")] is tv

    def test_heap_alias_unwraps_value(self):
        from interpreter.vm.vm_types import HeapObject

        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.heap_set(
            Address("mem_0"),
            HeapObject(
                fields={FieldName("0", FieldKind.INDEX): typed_from_runtime(None)}
            ),
        )
        vm.current_frame.var_heap_aliases[VarName("x")] = Pointer(
            base=Address("mem_0"), offset=0
        )
        tv = typed(42, scalar("Int"))
        update = StateUpdate(var_writes={VarName("x"): tv}, reasoning="test")
        apply_update(
            vm, update, type_env=_EMPTY_TYPE_ENV, conversion_rules=_IDENTITY_RULES
        )
        field_val = vm.heap_get(Address("mem_0")).fields[
            FieldName("0", FieldKind.INDEX)
        ]
        assert isinstance(field_val, TypedValue)
        assert field_val.value == 42

    def test_closure_binding_unwraps_value(self):
        from interpreter.vm.vm_types import ClosureEnvironment

        vm = VMState()
        env = ClosureEnvironment(bindings={})
        vm.closures[ClosureId("env_0")] = env
        vm.call_stack.append(
            StackFrame(
                function_name=FuncName("inner"),
                closure_env_id=ClosureId("env_0"),
                captured_var_names=frozenset({VarName("x")}),
            )
        )
        tv = typed(42, scalar("Int"))
        update = StateUpdate(var_writes={VarName("x"): tv}, reasoning="test")
        apply_update(
            vm, update, type_env=_EMPTY_TYPE_ENV, conversion_rules=_IDENTITY_RULES
        )
        assert env.bindings[VarName("x")] is tv
        assert vm.current_frame.local_vars[VarName("x")] is tv

    def test_register_coercion_when_declared_type_differs(self):
        from interpreter.types.coercion.default_conversion_rules import (
            DefaultTypeConversionRules,
        )

        type_env = TypeEnvironment(
            register_types=MappingProxyType({Register("%0"): scalar("Float")}),
            var_types=MappingProxyType({}),
        )
        rules = DefaultTypeConversionRules()
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        tv = typed(42, scalar("Int"))
        update = StateUpdate(register_writes={Register("%0"): tv}, reasoning="test")
        apply_update(vm, update, type_env=type_env, conversion_rules=rules)
        result = vm.current_frame.registers[Register("%0")]
        assert isinstance(result, TypedValue)
        assert isinstance(result.value, float)
        assert result.type == scalar("Float")


class TestFormatVal:
    def test_format_typed_int(self):
        from interpreter.run import _format_val

        assert _format_val(typed(42, scalar("Int"))) == "42"

    def test_format_typed_symbolic(self):
        from interpreter.run import _format_val

        sym = SymbolicValue(name="sym_0", type_hint="Int")
        assert "sym_0" in _format_val(typed(sym, UNKNOWN))
