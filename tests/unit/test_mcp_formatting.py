"""Tests for MCP server formatting -- converting internal types to JSON-friendly dicts."""

from __future__ import annotations

from interpreter.dataflow import Definition
from interpreter.interprocedural.types import (
    FieldEndpoint,
    FunctionEntry,
    InstructionLocation,
    NO_DEFINITION,
    ReturnEndpoint,
    VariableEndpoint,
)
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.types.typed_value import TypedValue
from interpreter.constants import TypeName
from interpreter.types.type_expr import ScalarType

from mcp_server.formatting import (
    format_typed_value,
    format_flow_endpoint,
    format_state_update,
    format_chain_node,
    format_vm_state_frame,
)


class TestFormatTypedValue:
    def test_int_value(self):
        tv = TypedValue(value=42, type=ScalarType(name=TypeName.INT))
        result = format_typed_value(tv)
        assert result == 42

    def test_string_value(self):
        tv = TypedValue(value="hello", type=ScalarType(name=TypeName.STRING))
        result = format_typed_value(tv)
        assert result == "hello"

    def test_complex_value_returns_dict(self):
        tv = TypedValue(value={"key": "val"}, type=ScalarType(name=TypeName.ANY))
        result = format_typed_value(tv)
        assert isinstance(result, dict)


class TestFormatFlowEndpoint:
    def test_variable_endpoint(self):
        ep = VariableEndpoint(name="x", definition=NO_DEFINITION)
        result = format_flow_endpoint(ep)
        assert result == {"name": "x", "type": "variable"}

    def test_return_endpoint(self):
        func = FunctionEntry(label=CodeLabel("func_f_0"), params=("x",))
        loc = InstructionLocation(
            block_label=CodeLabel("func_f_0"), instruction_index=5
        )
        ep = ReturnEndpoint(function=func, location=loc)
        result = format_flow_endpoint(ep)
        assert result == {"function": "func_f_0", "type": "return"}

    def test_field_endpoint(self):
        base = VariableEndpoint(name="self", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label=CodeLabel("b"), instruction_index=1)
        ep = FieldEndpoint(base=base, field="name", location=loc)
        result = format_flow_endpoint(ep)
        assert result == {"base": "self", "field": "name", "type": "field"}


class TestFormatChainNode:
    def test_leaf_node(self):
        from viz.panels.dataflow_graph_panel import ChainNode

        node = ChainNode(label="x \u2192 return(f)")
        result = format_chain_node(node)
        assert result == {"label": "x \u2192 return(f)", "children": []}

    def test_node_with_children(self):
        from viz.panels.dataflow_graph_panel import ChainNode

        child = ChainNode(label="a \u2192 return(add)")
        node = ChainNode(label="x \u2192 add(a=x)", children=[child])
        result = format_chain_node(node)
        assert result["label"] == "x \u2192 add(a=x)"
        assert len(result["children"]) == 1
        assert result["children"][0]["label"] == "a \u2192 return(add)"


class TestFormatStateUpdate:
    def test_empty_update(self):
        from interpreter.vm.vm_types import StateUpdate

        update = StateUpdate()
        result = format_state_update(update)
        assert result == {}

    def test_register_write(self):
        from interpreter.vm.vm_types import StateUpdate

        update = StateUpdate(register_writes={"%0": 42})
        result = format_state_update(update)
        assert result["registers"] == {"%0": 42}

    def test_var_write(self):
        from interpreter.vm.vm_types import StateUpdate

        update = StateUpdate(var_writes={"x": 10})
        result = format_state_update(update)
        assert result["variables"] == {"x": 10}

    def test_next_label(self):
        from interpreter.vm.vm_types import StateUpdate

        from interpreter.ir import CodeLabel

        update = StateUpdate(next_label=CodeLabel("func_f_0"))
        result = format_state_update(update)
        assert result["next_block"] == "func_f_0"
