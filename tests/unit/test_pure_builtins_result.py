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
from interpreter.typed_value import typed
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
        result = _builtin_len(["arr_0"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 1
        assert result.new_objects == []
        assert result.heap_writes == []

    def test_range_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_range([3], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == [0, 1, 2]
        assert result.new_objects == []

    def test_print_returns_builtin_result_with_none(self):
        vm = VMState()
        result = _builtin_print(["hello"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is None

    def test_int_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_int(["42"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 42

    def test_float_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_float(["3.14"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 3.14

    def test_str_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_str([42], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == "42"

    def test_bool_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_bool([1], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is True

    def test_abs_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_abs([-5], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 5

    def test_max_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_max([1, 5, 3], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 5

    def test_min_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_min([1, 5, 3], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 1

    def test_uncomputable_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_len([], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE
