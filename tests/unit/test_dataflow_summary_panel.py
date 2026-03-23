"""Tests for dataflow summary panel rendering helpers."""

from __future__ import annotations

from interpreter.ir import CodeLabel
from interpreter.interprocedural.types import (
    CallGraph,
    CallSite,
    FieldEndpoint,
    FunctionEntry,
    FunctionSummary,
    InterproceduralResult,
    NO_DEFINITION,
    ReturnEndpoint,
    SummaryKey,
    VariableEndpoint,
    ROOT_CONTEXT,
    InstructionLocation,
)
from viz.panels.dataflow_summary_panel import (
    render_endpoint,
    build_function_callers,
    build_function_callees,
    merge_flows_for_function,
)


class TestRenderEndpoint:
    def test_variable_endpoint(self):
        ep = VariableEndpoint(name="x", definition=NO_DEFINITION)
        assert render_endpoint(ep) == "x"

    def test_return_endpoint(self):
        func = FunctionEntry(label=CodeLabel("func_f_0"), params=("x",))
        loc = InstructionLocation(block_label=CodeLabel("func_f_0"), instruction_index=5)
        ep = ReturnEndpoint(function=func, location=loc)
        assert render_endpoint(ep) == "Return(func_f_0)"

    def test_field_endpoint(self):
        base = VariableEndpoint(name="self", definition=NO_DEFINITION)
        loc = InstructionLocation(block_label=CodeLabel("func_init_0"), instruction_index=3)
        ep = FieldEndpoint(base=base, field="name", location=loc)
        assert render_endpoint(ep) == "Field(self.name)"


class TestBuildCallers:
    def test_function_with_caller(self):
        f = FunctionEntry(label=CodeLabel("func_f_0"), params=("x",))
        g = FunctionEntry(label=CodeLabel("func_g_2"), params=("y",))
        loc = InstructionLocation(block_label=CodeLabel("func_g_2"), instruction_index=3)
        site = CallSite(
            caller=g,
            location=loc,
            callees=frozenset({f}),
            arg_operands=("%7",),
        )
        call_graph = CallGraph(
            functions=frozenset({f, g}), call_sites=frozenset({site})
        )
        callers = build_function_callers(f, call_graph)
        assert callers == {"func_g_2"}

    def test_function_with_no_callers(self):
        f = FunctionEntry(label=CodeLabel("func_f_0"), params=("x",))
        call_graph = CallGraph(functions=frozenset({f}), call_sites=frozenset())
        callers = build_function_callers(f, call_graph)
        assert callers == set()


class TestBuildCallees:
    def test_function_with_callee(self):
        f = FunctionEntry(label=CodeLabel("func_f_0"), params=("x",))
        g = FunctionEntry(label=CodeLabel("func_g_2"), params=("y",))
        loc = InstructionLocation(block_label=CodeLabel("func_g_2"), instruction_index=3)
        site = CallSite(
            caller=g,
            location=loc,
            callees=frozenset({f}),
            arg_operands=("%7",),
        )
        call_graph = CallGraph(
            functions=frozenset({f, g}), call_sites=frozenset({site})
        )
        callees = build_function_callees(g, call_graph)
        assert callees == {"func_f_0"}


class TestMergeFlows:
    def test_merges_across_contexts(self):
        f = FunctionEntry(label=CodeLabel("func_f_0"), params=("x",))
        flow1 = (
            VariableEndpoint(name="x", definition=NO_DEFINITION),
            ReturnEndpoint(
                function=f,
                location=InstructionLocation(
                    block_label="func_f_0", instruction_index=5
                ),
            ),
        )
        summary1 = FunctionSummary(
            function=f, context=ROOT_CONTEXT, flows=frozenset({flow1})
        )
        key1 = SummaryKey(function=f, context=ROOT_CONTEXT)
        summaries = {key1: summary1}
        merged = merge_flows_for_function(f, summaries)
        assert len(merged) == 1
