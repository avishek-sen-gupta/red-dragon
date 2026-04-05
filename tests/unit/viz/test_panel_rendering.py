"""Tests for TUI panel rendering with domain newtype keys.

Exercises all sorted() paths in viz panels to catch TypeError from
domain objects (Register, CodeLabel, VarName, Address, FieldName)
that lack __lt__. The TUI layer must use key=lambda for ordering,
never rely on domain object comparison.
"""

from __future__ import annotations

from interpreter.address import Address
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.types.typed_value import TypedValue
from interpreter.constants import TypeName
from interpreter.types.type_expr import ScalarType
from interpreter.var_name import VarName
from interpreter.vm.vm_types import HeapObject, StackFrame

from viz.panels.vm_state_panel import _format_value


def _int_val(n: int) -> TypedValue:
    return TypedValue(value=n, type=ScalarType(TypeName.INT))


def _str_val(s: str) -> TypedValue:
    return TypedValue(value=s, type=ScalarType(TypeName.STRING))


class TestVMStatePanelSorting:
    """Verify that all sorted() paths in VMStatePanel work with newtype keys."""

    def test_registers_sort_by_str(self):
        """sorted(frame.registers.items(), key=...) must not crash."""
        regs = {
            Register("%3"): _int_val(10),
            Register("%1"): _int_val(20),
            Register("%2"): _int_val(30),
        }
        result = sorted(regs.items(), key=lambda kv: str(kv[0]))
        assert [str(k) for k, _ in result] == ["%1", "%2", "%3"]

    def test_local_vars_sort_by_str(self):
        """sorted(frame.local_vars.items(), key=...) must not crash."""
        local_vars = {
            VarName("z"): _int_val(1),
            VarName("a"): _int_val(2),
            VarName("m"): _int_val(3),
        }
        result = sorted(local_vars.items(), key=lambda kv: str(kv[0]))
        assert [str(k) for k, _ in result] == ["a", "m", "z"]

    def test_heap_items_sort_by_str(self):
        """sorted(vm.heap_items(), key=...) must not crash."""
        heap = {
            Address("obj_2"): HeapObject(fields={}, type_hint="Foo"),
            Address("obj_0"): HeapObject(fields={}, type_hint="Bar"),
            Address("obj_1"): HeapObject(fields={}, type_hint="Baz"),
        }
        result = sorted(heap.items(), key=lambda kv: str(kv[0]))
        assert [str(k) for k, _ in result] == ["obj_0", "obj_1", "obj_2"]

    def test_heap_fields_sort_by_str(self):
        """sorted(obj.fields.items(), key=...) must not crash."""
        fields = {
            FieldName("name"): _str_val("alice"),
            FieldName("age"): _int_val(30),
            FieldName("id"): _int_val(1),
        }
        result = sorted(fields.items(), key=lambda kv: str(kv[0]))
        assert [str(k) for k, _ in result] == ["age", "id", "name"]

    def test_registers_without_key_raises(self):
        """Bare sorted() on Register keys must raise TypeError."""
        regs = {
            Register("%b"): _int_val(1),
            Register("%a"): _int_val(2),
        }
        try:
            sorted(regs.items())
            assert False, "Expected TypeError"
        except TypeError:
            pass


class TestCodeLabelSorting:
    """Verify CodeLabel sorting in dataflow panels uses str key."""

    def test_code_labels_sort_by_str(self):
        labels = [CodeLabel("func_z_0"), CodeLabel("func_a_0"), CodeLabel("func_m_0")]
        result = sorted(labels, key=lambda l: str(l))
        assert [str(l) for l in result] == ["func_a_0", "func_m_0", "func_z_0"]

    def test_code_labels_without_key_raises(self):
        """Bare sorted() on CodeLabel must raise TypeError."""
        labels = [CodeLabel("b"), CodeLabel("a")]
        try:
            sorted(labels)
            assert False, "Expected TypeError"
        except TypeError:
            pass


class TestFormatValue:
    """Exercise _format_value with various VM value types."""

    def test_typed_value_int(self):
        assert _format_value(_int_val(42)) == "42"

    def test_typed_value_string_short(self):
        assert _format_value(_str_val("hello")) == '"hello"'

    def test_typed_value_string_long(self):
        long_str = "a" * 50
        result = _format_value(_str_val(long_str))
        assert result.startswith('"aaa')
        assert result.endswith('..."')

    def test_plain_int(self):
        assert _format_value(42) == "42"

    def test_plain_none(self):
        assert _format_value(None) == "None"
