"""Unit tests verifying pure builtins return BuiltinResult with empty side-effect lists."""

from interpreter.builtins import (
    _builtin_len,
    _builtin_range,
    _builtin_print,
    _builtin_int,
    _builtin_float,
    _builtin_str,
    _builtin_bool,
    _builtin_abs,
    _builtin_max,
    _builtin_min,
)
from interpreter.vm import VMState, Operators
from interpreter.vm_types import BuiltinResult, HeapObject
from interpreter.typed_value import typed, typed_from_runtime
from interpreter.type_expr import scalar
from interpreter.constants import TypeName


class TestPureBuiltinsReturnBuiltinResult:
    def test_len_returns_builtin_result(self):
        vm = VMState()
        vm.heap["arr_0"] = HeapObject(
            type_hint="array",
            fields={
                "0": typed(10, scalar(TypeName.INT)),
                "length": typed(1, scalar(TypeName.INT)),
            },
        )
        result = _builtin_len([typed_from_runtime("arr_0")], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 1
        assert result.new_objects == []
        assert result.heap_writes == []

    def test_range_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_range([typed_from_runtime(3)], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == [0, 1, 2]
        assert result.new_objects == []

    def test_print_returns_builtin_result_with_none(self):
        vm = VMState()
        result = _builtin_print([typed_from_runtime("hello")], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is None

    def test_int_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_int([typed_from_runtime("42")], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 42

    def test_float_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_float([typed_from_runtime("3.14")], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 3.14

    def test_str_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_str([typed_from_runtime(42)], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == "42"

    def test_bool_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_bool([typed_from_runtime(1)], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is True

    def test_abs_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_abs([typed_from_runtime(-5)], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 5

    def test_max_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_max(
            [typed_from_runtime(1), typed_from_runtime(5), typed_from_runtime(3)], vm
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == 5

    def test_min_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_min(
            [typed_from_runtime(1), typed_from_runtime(5), typed_from_runtime(3)], vm
        )
        assert isinstance(result, BuiltinResult)
        assert result.value == 1

    def test_uncomputable_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_len([], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE
