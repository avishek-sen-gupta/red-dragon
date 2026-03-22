"""Tests for _unwrap_builtin_result helper."""

from interpreter.vm.executor import _unwrap_builtin_result
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.types.type_expr import pointer, scalar
from interpreter.vm.vm_types import BuiltinResult, Pointer


class TestUnwrapBuiltinResult:
    def test_passes_through_typed_value(self):
        tv = typed(Pointer(base="arr_0", offset=0), pointer(scalar("Array")))
        result = BuiltinResult(value=tv)
        assert _unwrap_builtin_result(result, "test") is tv

    def test_wraps_bare_int_via_typed_from_runtime(self):
        result = BuiltinResult(value=42)
        tv = _unwrap_builtin_result(result, "len")
        assert isinstance(tv, TypedValue)
        assert tv.value == 42

    def test_wraps_bare_string_via_typed_from_runtime(self):
        result = BuiltinResult(value="hello")
        tv = _unwrap_builtin_result(result, "str")
        assert isinstance(tv, TypedValue)
        assert tv.value == "hello"

    def test_wraps_none_result(self):
        result = BuiltinResult(value=None)
        tv = _unwrap_builtin_result(result, "print")
        assert isinstance(tv, TypedValue)
