"""Tests for whole-program graph panel rendering."""

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
from interpreter.ir import IRInstruction, Opcode
from viz.panels.dataflow_graph_panel import annotate_endpoint, render_graph_lines


class TestAnnotateEndpoint:
    def test_named_variable_no_annotation(self):
        ep = VariableEndpoint(name="x", definition=NO_DEFINITION)
        assert annotate_endpoint(ep, None) == "x"

    def test_register_with_call_definition(self):
        inst = IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg="%8",
            operands=["f", "%7"],
        )
        defn = Definition(
            variable="%8",
            block_label="func_g_2",
            instruction_index=3,
            instruction=inst,
        )
        ep = VariableEndpoint(name="%8", definition=defn)
        assert annotate_endpoint(ep, None) == "%8 (call result: f)"

    def test_register_with_non_call_definition(self):
        inst = IRInstruction(
            opcode=Opcode.BINOP,
            result_reg="%3",
            operands=["+", "%1", "%2"],
        )
        defn = Definition(
            variable="%3",
            block_label="func_f_0",
            instruction_index=4,
            instruction=inst,
        )
        ep = VariableEndpoint(name="%3", definition=defn)
        assert annotate_endpoint(ep, None) == "%3"

    def test_return_endpoint(self):
        func = FunctionEntry(label="func_f_0", params=("x",))
        loc = InstructionLocation(block_label="func_f_0", instruction_index=5)
        ep = ReturnEndpoint(function=func, location=loc)
        assert annotate_endpoint(ep, None) == "Return(func_f_0)"

    def test_field_endpoint(self):
        base = VariableEndpoint(name="self", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label="b", instruction_index=1)
        ep = FieldEndpoint(base=base, field="name", location=loc)
        assert annotate_endpoint(ep, None) == "Field(self.name)"


class TestRenderGraphLines:
    def test_renders_edges_grouped_by_source(self):
        f = FunctionEntry(label="func_f_0", params=("x",))
        loc = InstructionLocation(block_label="func_f_0", instruction_index=5)
        x_ep = VariableEndpoint(name="x", definition=NO_DEFINITION)
        ret_ep = ReturnEndpoint(function=f, location=loc)
        graph = {x_ep: frozenset({ret_ep})}
        lines = render_graph_lines(graph, None)
        assert any("x" in line and "Return(func_f_0)" in line for line in lines)

    def test_empty_graph(self):
        lines = render_graph_lines({}, None)
        assert len(lines) == 0
