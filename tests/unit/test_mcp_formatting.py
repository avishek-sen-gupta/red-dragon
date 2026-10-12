"""Tests for MCP server formatting -- converting internal types to JSON-friendly dicts."""

from __future__ import annotations

from interpreter.constants import FoundationTypeName
from interpreter.register import Register
from interpreter.types.type_expr import ScalarType
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from mcp_server.formatting import (
    format_state_update,
    format_typed_value,
)


class TestFormatTypedValue:
    def test_int_value(self):
        tv = TypedValue(value=42, type=ScalarType(name=FoundationTypeName.INT))
        result = format_typed_value(tv)
        assert result == 42

    def test_string_value(self):
        tv = TypedValue(value="hello", type=ScalarType(name=FoundationTypeName.STRING))
        result = format_typed_value(tv)
        assert result == "hello"

    def test_complex_value_returns_dict(self):
        tv = TypedValue(
            value={"key": "val"}, type=ScalarType(name=FoundationTypeName.ANY)
        )
        result = format_typed_value(tv)
        assert isinstance(result, dict)


class TestFormatStateUpdate:
    def test_empty_update(self):
        from interpreter.vm.vm_types import StateUpdate

        update = StateUpdate()
        result = format_state_update(update)
        assert result == {}

    def test_register_write(self):
        from interpreter.vm.vm_types import StateUpdate

        update = StateUpdate(register_writes={Register("%0"): 42})
        result = format_state_update(update)
        assert result["registers"] == {"%0": 42}

    def test_var_write(self):
        from interpreter.vm.vm_types import StateUpdate

        update = StateUpdate(var_writes={VarName("x"): 10})
        result = format_state_update(update)
        assert result["variables"] == {"x": 10}

    def test_next_label(self):
        from interpreter.ir import CodeLabel
        from interpreter.vm.vm_types import StateUpdate

        update = StateUpdate(next_label=CodeLabel("func_f_0"))
        result = format_state_update(update)
        assert result["next_block"] == "func_f_0"
