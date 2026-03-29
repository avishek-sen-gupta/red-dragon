"""Unit tests for TypedValue dataclass and factory helpers."""

from interpreter.types.type_expr import UNKNOWN, ScalarType, scalar
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.address import Address
from interpreter.vm.vm_types import Pointer, SymbolicValue


class TestTypedValue:
    def test_creation_with_int(self):
        tv = TypedValue(value=42, type=scalar("Int"))
        assert tv.value == 42
        assert tv.type == scalar("Int")

    def test_frozen(self):
        tv = TypedValue(value=42, type=scalar("Int"))
        try:
            tv.value = 99
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_equality(self):
        a = TypedValue(value=42, type=scalar("Int"))
        b = TypedValue(value=42, type=scalar("Int"))
        assert a == b

    def test_inequality_different_type(self):
        a = TypedValue(value=42, type=scalar("Int"))
        b = TypedValue(value=42, type=scalar("Float"))
        assert a != b

    def test_wraps_symbolic_value(self):
        sym = SymbolicValue(name="sym_0", type_hint="Int")
        tv = TypedValue(value=sym, type=UNKNOWN)
        assert tv.value is sym
        assert tv.type == UNKNOWN

    def test_wraps_pointer(self):
        ptr = Pointer(base=Address("obj_0"), offset=4)
        tv = TypedValue(value=ptr, type=UNKNOWN)
        assert tv.value is ptr

    def test_wraps_none(self):
        tv = TypedValue(value=None, type=UNKNOWN)
        assert tv.value is None
        assert tv.type == UNKNOWN


class TestTypedFactory:
    def test_typed_with_explicit_type(self):
        tv = typed(42, scalar("Int"))
        assert tv.value == 42
        assert tv.type == scalar("Int")

    def test_typed_default_unknown(self):
        tv = typed("hello")
        assert tv.value == "hello"
        assert tv.type == UNKNOWN

    def test_typed_from_runtime_int(self):
        tv = typed_from_runtime(42)
        assert tv.value == 42
        assert tv.type == scalar("Int")

    def test_typed_from_runtime_float(self):
        tv = typed_from_runtime(3.14)
        assert tv.value == 3.14
        assert tv.type == scalar("Float")

    def test_typed_from_runtime_string(self):
        tv = typed_from_runtime("hello")
        assert tv.value == "hello"
        assert tv.type == scalar("String")

    def test_typed_from_runtime_bool(self):
        tv = typed_from_runtime(True)
        assert tv.value is True
        assert tv.type == scalar("Bool")

    def test_typed_from_runtime_unknown_type(self):
        tv = typed_from_runtime([1, 2, 3])
        assert tv.value == [1, 2, 3]
        assert tv.type == UNKNOWN

    def test_typed_from_runtime_none(self):
        tv = typed_from_runtime(None)
        assert tv.value is None
        assert tv.type == UNKNOWN

    def test_typed_from_runtime_symbolic(self):
        sym = SymbolicValue(name="sym_0")
        tv = typed_from_runtime(sym)
        assert tv.value is sym
        assert tv.type == UNKNOWN
