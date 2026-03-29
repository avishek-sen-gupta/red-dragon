"""Unit tests for return_value TypedValue migration."""

from types import MappingProxyType

from interpreter.constants import TypeName
from interpreter.types.coercion.identity_conversion_rules import IdentityConversionRules
from interpreter.ir import IRInstruction, Opcode
from interpreter.vm.executor import _handle_return, _default_handler_context
from interpreter.types.type_environment import TypeEnvironment
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.vm.vm import materialize_raw_update
from interpreter.vm.vm_types import StateUpdate, SymbolicValue, VMState, StackFrame
from interpreter.register import Register
from interpreter.func_name import FuncName

_EMPTY_TYPE_ENV = TypeEnvironment(
    register_types=MappingProxyType({}),
    var_types=MappingProxyType({}),
)
_IDENTITY_RULES = IdentityConversionRules()


class TestHandleReturnTypedValue:
    """Tests for _handle_return producing TypedValue in return_value."""

    def test_return_with_int_operand(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.current_frame.registers[Register("%0")] = typed(42, scalar(TypeName.INT))
        inst = IRInstruction(opcode=Opcode.RETURN, operands=["%0"])
        result = _handle_return(inst, vm, _default_handler_context())
        rv = result.update.return_value
        assert isinstance(rv, TypedValue)
        assert rv.value == 42

    def test_return_with_none_operand(self):
        """return None -> typed(None, UNKNOWN), distinguishable from Void."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        vm.current_frame.registers[Register("%0")] = typed(None, UNKNOWN)
        inst = IRInstruction(opcode=Opcode.RETURN, operands=["%0"])
        result = _handle_return(inst, vm, _default_handler_context())
        rv = result.update.return_value
        assert isinstance(rv, TypedValue)
        assert rv.value is None
        assert rv.type == UNKNOWN
        assert rv.type != scalar(TypeName.VOID)

    def test_return_without_operands_is_void(self):
        """RETURN with no operands -> typed(None, scalar('Void'))."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        inst = IRInstruction(opcode=Opcode.RETURN, operands=[])
        result = _handle_return(inst, vm, _default_handler_context())
        rv = result.update.return_value
        assert isinstance(rv, TypedValue)
        assert rv.value is None
        assert rv.type == scalar(TypeName.VOID)

    def test_void_and_none_are_distinguishable(self):
        """Void and None return values have different types."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))

        # Void (no operands)
        void_inst = IRInstruction(opcode=Opcode.RETURN, operands=[])
        void_result = _handle_return(void_inst, vm, _default_handler_context())
        void_rv = void_result.update.return_value

        # None (explicit return None)
        vm.current_frame.registers[Register("%0")] = typed(None, UNKNOWN)
        none_inst = IRInstruction(opcode=Opcode.RETURN, operands=["%0"])
        none_result = _handle_return(none_inst, vm, _default_handler_context())
        none_rv = none_result.update.return_value

        assert void_rv.type == scalar(TypeName.VOID)
        assert none_rv.type != scalar(TypeName.VOID)
        assert void_rv.type != none_rv.type


class TestMaterializeReturnValue:
    """Tests for materialize_raw_update handling return_value."""

    def test_raw_int_return_value_materialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(return_value=42, call_pop=True, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        rv = result.return_value
        assert isinstance(rv, TypedValue)
        assert rv.value == 42
        assert rv.type == scalar(TypeName.INT)

    def test_default_return_value_is_void(self):
        """StateUpdate without explicit return_value defaults to Void."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        raw = StateUpdate(reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert isinstance(result.return_value, TypedValue)
        assert result.return_value.type == scalar(TypeName.VOID)

    def test_symbolic_dict_return_value_materialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        sym_dict = {"__symbolic__": True, "name": "sym_0", "type_hint": "Int"}
        raw = StateUpdate(return_value=sym_dict, call_pop=True, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        rv = result.return_value
        assert isinstance(rv, TypedValue)
        assert isinstance(rv.value, SymbolicValue)
        assert rv.value.name == "sym_0"

    def test_already_typed_return_value_passes_through(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name=FuncName("main")))
        tv = typed(42, scalar(TypeName.INT))
        raw = StateUpdate(return_value=tv, call_pop=True, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert result.return_value is tv
