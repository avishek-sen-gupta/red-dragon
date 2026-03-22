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

from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.registry import build_registry
from viz.panels.dataflow_graph_panel import (
    TopLevelCall,
    ChainNode,
    build_call_chain,
    find_top_level_call_sites,
    trace_reg_to_var,
)


def _analyze(source: str, language: Language = Language.PYTHON):
    """Helper: run full pipeline and return (cfg, result)."""
    frontend = get_frontend(language)
    ir = frontend.lower(source.encode())
    cfg = build_cfg(ir)
    registry = build_registry(
        ir,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    result = analyze_interprocedural(cfg, registry)
    return cfg, result


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


class TestFindTopLevelCallSites:
    def test_single_top_level_call(self):
        source = "def f(x):\n    return x\nresult = f(5)\n"
        cfg, result = _analyze(source)
        top_calls = find_top_level_call_sites(cfg, result.call_graph)
        assert len(top_calls) >= 1
        call = top_calls[0]
        assert "f" in call.callee_label or "func_f" in call.callee_label
        assert call.result_var == "result"

    def test_no_functions_no_top_level_calls(self):
        source = "x = 1\ny = x + 1\n"
        cfg, result = _analyze(source)
        top_calls = find_top_level_call_sites(cfg, result.call_graph)
        assert len(top_calls) == 0

    def test_multi_function_finds_outermost_call(self):
        source = (
            "def add(a, b):\n    return a + b\n"
            "def double(x):\n    return add(x, x)\n"
            "result = double(5)\n"
        )
        cfg, result = _analyze(source)
        top_calls = find_top_level_call_sites(cfg, result.call_graph)
        assert len(top_calls) >= 1
        assert any("double" in c.callee_label for c in top_calls)


class TestTraceRegToVar:
    def test_traces_load_var(self):
        source = "def f(x):\n    return x\nresult = f(5)\n"
        cfg, _ = _analyze(source)
        found = False
        for label, block in cfg.blocks.items():
            for inst in block.instructions:
                if inst.opcode == Opcode.LOAD_VAR and inst.result_reg:
                    traced = trace_reg_to_var(inst.result_reg, cfg, label)
                    assert traced == str(inst.operands[0])
                    found = True
                    break
            if found:
                break
        assert found, "No LOAD_VAR found in test program"


def _collect_labels(nodes: list) -> list[str]:
    """Collect all labels from a ChainNode tree."""
    result = []
    for n in nodes:
        result.append(n.label)
        result.extend(_collect_labels(n.children))
    return result


class TestBuildCallChain:
    def test_simple_function_shows_param_to_return(self):
        """f(x) -> return x+1: chain should show x -> return(f)."""
        source = "def f(x):\n    return x + 1\nf(5)\n"
        cfg, result = _analyze(source)
        f_entry = [f for f in result.call_graph.functions if "f" in f.label][0]
        nodes = build_call_chain(
            f_entry, result.call_graph, result.summaries, cfg, set()
        )
        assert len(nodes) >= 1
        all_labels = _collect_labels(nodes)
        assert any("x" in lbl and "return" in lbl.lower() for lbl in all_labels)

    def test_caller_callee_chain_has_nested_nodes(self):
        """double(x) calls add(x, x): chain should have nested subtree."""
        source = (
            "def add(a, b):\n    return a + b\n"
            "def double(x):\n    return add(x, x)\n"
            "double(5)\n"
        )
        cfg, result = _analyze(source)
        double_entry = [f for f in result.call_graph.functions if "double" in f.label][
            0
        ]
        nodes = build_call_chain(
            double_entry, result.call_graph, result.summaries, cfg, set()
        )
        has_nested = any(len(n.children) > 0 for n in nodes)
        assert has_nested, f"Expected nested nodes, got: {[n.label for n in nodes]}"

    def test_recursive_function_stops_at_guard(self):
        """factorial(n) calls factorial(n-1): should not infinite-loop.

        The recursive call passes n-1 (a BINOP result), not n directly,
        so _param_inner_calls won't match. The key invariant is that
        build_call_chain terminates and produces a finite tree.
        """
        source = (
            "def factorial(n):\n"
            "    if n <= 1:\n"
            "        return 1\n"
            "    return n * factorial(n - 1)\n"
            "factorial(5)\n"
        )
        cfg, result = _analyze(source)
        f_entry = [f for f in result.call_graph.functions if "factorial" in f.label][0]
        nodes = build_call_chain(
            f_entry, result.call_graph, result.summaries, cfg, set()
        )
        all_labels = _collect_labels(nodes)
        # Must terminate and produce at least the return flow
        assert len(all_labels) >= 1

    def test_direct_passthrough_recursion_hits_guard(self):
        """g(x) calls g(x) directly: chain should hit the recursion guard."""
        source = "def g(x):\n" "    return g(x)\n" "g(5)\n"
        cfg, result = _analyze(source)
        g_entry = [f for f in result.call_graph.functions if "g" in f.label][0]
        nodes = build_call_chain(
            g_entry, result.call_graph, result.summaries, cfg, set()
        )
        all_labels = _collect_labels(nodes)
        assert any(
            "recursive" in lbl.lower() for lbl in all_labels
        ), f"Expected recursion guard, got: {all_labels}"
