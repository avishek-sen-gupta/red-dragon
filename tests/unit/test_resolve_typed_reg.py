"""Unit tests for _resolve_typed_reg — type-aware register resolution."""

from types import MappingProxyType

from interpreter.constants import TypeName
from interpreter.default_conversion_rules import DefaultConversionRules
from interpreter.function_signature import FunctionSignature
from interpreter.identity_conversion_rules import IdentityConversionRules
from interpreter.type_environment import TypeEnvironment
from interpreter.vm import VMState, _resolve_typed_reg, _runtime_type_name
from interpreter.vm_types import StackFrame


def _make_vm() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


def _type_env_with(register_types: dict[str, str]) -> TypeEnvironment:
    return TypeEnvironment(
        register_types=MappingProxyType(register_types),
        var_types=MappingProxyType({}),
        func_signatures=MappingProxyType({}),
    )


_EMPTY_TYPE_ENV = _type_env_with({})
_DEFAULT_RULES = DefaultConversionRules()
_IDENTITY_RULES = IdentityConversionRules()


class TestRuntimeTypeName:
    def test_int(self):
        assert _runtime_type_name(42) == TypeName.INT

    def test_float(self):
        assert _runtime_type_name(3.14) == TypeName.FLOAT

    def test_bool(self):
        assert _runtime_type_name(True) == TypeName.BOOL

    def test_str(self):
        assert _runtime_type_name("hello") == TypeName.STRING

    def test_unknown_returns_empty(self):
        assert _runtime_type_name([1, 2, 3]) == ""

    def test_none_returns_empty(self):
        assert _runtime_type_name(None) == ""


class TestResolveTypedReg:
    def test_float_coerced_to_int_when_type_env_says_int(self):
        vm = _make_vm()
        vm.current_frame.registers["%0"] = 2.0
        type_env = _type_env_with({"%0": TypeName.INT})

        result = _resolve_typed_reg(vm, "%0", type_env, _DEFAULT_RULES)

        assert result == 2
        assert isinstance(result, int)

    def test_int_coerced_to_float_when_type_env_says_float(self):
        vm = _make_vm()
        vm.current_frame.registers["%0"] = 2
        type_env = _type_env_with({"%0": TypeName.FLOAT})

        result = _resolve_typed_reg(vm, "%0", type_env, _DEFAULT_RULES)

        assert result == 2.0
        assert isinstance(result, float)

    def test_no_coercion_when_type_env_empty(self):
        vm = _make_vm()
        vm.current_frame.registers["%0"] = 2.0

        result = _resolve_typed_reg(vm, "%0", _EMPTY_TYPE_ENV, _DEFAULT_RULES)

        assert result == 2.0
        assert isinstance(result, float)

    def test_no_coercion_when_runtime_matches_target(self):
        vm = _make_vm()
        vm.current_frame.registers["%0"] = 42
        type_env = _type_env_with({"%0": TypeName.INT})

        result = _resolve_typed_reg(vm, "%0", type_env, _DEFAULT_RULES)

        assert result == 42
        assert isinstance(result, int)

    def test_non_register_operand_passes_through(self):
        vm = _make_vm()
        type_env = _type_env_with({"%0": TypeName.INT})

        result = _resolve_typed_reg(vm, "hello", type_env, _DEFAULT_RULES)

        assert result == "hello"

    def test_identity_rules_do_not_coerce(self):
        vm = _make_vm()
        vm.current_frame.registers["%0"] = 2.0
        type_env = _type_env_with({"%0": TypeName.INT})

        result = _resolve_typed_reg(vm, "%0", type_env, _IDENTITY_RULES)

        assert result == 2.0
        assert isinstance(result, float)

    def test_bool_coerced_to_int(self):
        vm = _make_vm()
        vm.current_frame.registers["%0"] = True
        type_env = _type_env_with({"%0": TypeName.INT})

        result = _resolve_typed_reg(vm, "%0", type_env, _DEFAULT_RULES)

        assert result == 1
        assert isinstance(result, int)
        assert not isinstance(result, bool)

    def test_unregistered_register_passes_through(self):
        """Register not in VM returns the register name as-is."""
        vm = _make_vm()
        type_env = _type_env_with({"%unknown": TypeName.INT})

        result = _resolve_typed_reg(vm, "%unknown", type_env, _DEFAULT_RULES)

        assert result == "%unknown"
