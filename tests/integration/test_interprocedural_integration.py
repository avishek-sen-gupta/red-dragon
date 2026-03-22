"""Integration tests for interprocedural dataflow analysis.

Each test runs a REAL language program through the full pipeline:
source -> frontend.lower() -> build_cfg() -> build_registry() -> analyze_interprocedural() -> query.

Assertions target STRUCTURAL properties (call graph has edges, summaries exist,
graphs are non-empty) rather than exact register/label names.
"""

from __future__ import annotations

import pytest

from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.types import (
    FieldEndpoint,
    InterproceduralResult,
    ReturnEndpoint,
    VariableEndpoint,
)
from interpreter.registry import build_registry


def _analyze_source(source: str, language: Language) -> InterproceduralResult:
    """Parse, lower, build CFG/registry, run interprocedural analysis."""
    frontend = get_frontend(language)
    ir_instructions = frontend.lower(source.encode())
    cfg = build_cfg(ir_instructions)
    registry = build_registry(
        ir_instructions,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    return analyze_interprocedural(cfg, registry)


class TestPythonTwoFunctionChain:
    """Python: simple caller -> callee chain."""

    SOURCE = """\
def add(a, b):
    return a + b

result = add(3, 4)
"""

    def test_call_graph_has_call_sites(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        assert len(result.call_graph.call_sites) > 0, "Expected at least one call site"

    def test_call_graph_has_add_function(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        func_labels = {f.label for f in result.call_graph.functions}
        assert any(
            "add" in label for label in func_labels
        ), f"Expected 'add' in function labels, got {func_labels}"

    def test_analysis_completes(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        assert isinstance(result, InterproceduralResult)


class TestPythonOOPConstructor:
    """Python: class with constructor."""

    SOURCE = """\
class Dog:
    def __init__(self, name):
        self.name = name

d = Dog("Rex")
"""

    def test_call_graph_has_constructor_call(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        assert len(result.call_graph.call_sites) > 0, "Expected constructor call site"

    def test_call_graph_has_init_function(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        func_labels = {f.label for f in result.call_graph.functions}
        assert any(
            "__init__" in label for label in func_labels
        ), f"Expected '__init__' in function labels, got {func_labels}"


class TestPythonRecursiveFunction:
    """Python: recursive function -- summaries must converge."""

    SOURCE = """\
def countdown(n):
    if n <= 0:
        return 0
    return countdown(n - 1)

r = countdown(5)
"""

    def test_call_graph_has_recursive_edge(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        countdown_entries = [
            f for f in result.call_graph.functions if "countdown" in f.label
        ]
        assert len(countdown_entries) > 0, "Expected countdown function entry"

        countdown_entry = countdown_entries[0]
        recursive_sites = [
            site
            for site in result.call_graph.call_sites
            if site.caller == countdown_entry and countdown_entry in site.callees
        ]
        assert (
            len(recursive_sites) > 0
        ), "Expected recursive call site (countdown -> countdown)"

    def test_summaries_converge(self):
        """Fixpoint must terminate -- no infinite loop."""
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        assert isinstance(result, InterproceduralResult)


class TestRustTwoFunctionChain:
    """Rust: cross-language -- same analysis works on Rust IR."""

    SOURCE = """\
fn add(a: i32, b: i32) -> i32 {
    a + b
}
let r = add(3, 4);
"""

    def test_call_graph_has_call_sites(self):
        result = _analyze_source(self.SOURCE, Language.RUST)
        assert len(result.call_graph.call_sites) > 0, "Expected at least one call site"

    def test_call_graph_has_add_function(self):
        result = _analyze_source(self.SOURCE, Language.RUST)
        func_labels = {f.label for f in result.call_graph.functions}
        assert any(
            "add" in label for label in func_labels
        ), f"Expected 'add' in function labels, got {func_labels}"


class TestPythonMultiFunctionChain:
    """Python: three-level call chain g -> f."""

    SOURCE = """\
def f(x):
    return x + 1

def g(y):
    return f(y) + 2

result = g(10)
"""

    def test_call_graph_has_g_to_f_edge(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        g_calls_f = any(
            "g" in site.caller.label and any("f" in c.label for c in site.callees)
            for site in result.call_graph.call_sites
        )
        assert g_calls_f, (
            f"Expected g->f edge. Call sites: "
            f"{[(site.caller.label, [c.label for c in site.callees]) for site in result.call_graph.call_sites]}"
        )

    def test_summaries_exist(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        assert len(result.summaries) > 0, "Expected non-empty summaries"

    def test_program_graphs_non_empty(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        has_flows = (
            len(result.raw_program_graph) > 0 or len(result.whole_program_graph) > 0
        )
        assert has_flows, "Expected at least some flows in program graphs"


class TestQueryOnRealProgram:
    """Verify query interface works on real analysis results."""

    SOURCE = """\
def f(x):
    return x + 1

def g(y):
    return f(y) + 2

result = g(10)
"""

    def test_call_graph_has_functions(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        assert len(result.call_graph.functions) > 0

    def test_call_graph_has_call_sites(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        assert len(result.call_graph.call_sites) > 0

    def test_summaries_non_empty(self):
        result = _analyze_source(self.SOURCE, Language.PYTHON)
        assert len(result.summaries) > 0


def _extract_summary_flows(result: InterproceduralResult, func_name: str):
    """Extract (source_name, endpoint_type) pairs for a named function's summary flows."""
    flows = []
    for key, summary in result.summaries.items():
        if func_name not in key.function.label:
            continue
        for src, dst in summary.flows:
            flows.append((src, dst))
    return flows


class TestParamToReturnFlowsPython:
    """Assert specific param→return flows from real Python programs."""

    def test_identity_function_param_flows_to_return(self):
        """def f(x): return x → x flows to return."""
        result = _analyze_source("def f(x):\n    return x\nf(1)\n", Language.PYTHON)
        flows = _extract_summary_flows(result, "f")
        param_to_return = [
            (src, dst)
            for src, dst in flows
            if isinstance(src, VariableEndpoint) and isinstance(dst, ReturnEndpoint)
        ]
        assert len(param_to_return) == 1
        assert param_to_return[0][0].name == "x"

    def test_computation_param_flows_through_binop_to_return(self):
        """def inc(x): return x + 1 → x flows to return through BINOP."""
        result = _analyze_source(
            "def inc(x):\n    return x + 1\ninc(5)\n", Language.PYTHON
        )
        flows = _extract_summary_flows(result, "inc")
        param_to_return = [
            (src, dst)
            for src, dst in flows
            if isinstance(src, VariableEndpoint) and isinstance(dst, ReturnEndpoint)
        ]
        assert len(param_to_return) == 1
        assert param_to_return[0][0].name == "x"

    def test_two_params_both_flow_to_return(self):
        """def add(a, b): return a + b → both a and b flow to return."""
        result = _analyze_source(
            "def add(a, b):\n    return a + b\nadd(1, 2)\n", Language.PYTHON
        )
        flows = _extract_summary_flows(result, "add")
        param_names = {
            src.name
            for src, dst in flows
            if isinstance(src, VariableEndpoint) and isinstance(dst, ReturnEndpoint)
        }
        assert param_names == {"a", "b"}

    def test_constant_return_has_no_param_flows(self):
        """def const(): return 42 → no param flows."""
        result = _analyze_source(
            "def const():\n    return 42\nconst()\n", Language.PYTHON
        )
        flows = _extract_summary_flows(result, "const")
        param_to_return = [
            (src, dst)
            for src, dst in flows
            if isinstance(src, VariableEndpoint) and isinstance(dst, ReturnEndpoint)
        ]
        assert len(param_to_return) == 0

    def test_field_write_flow(self):
        """def set_name(self, name): self.name = name → name flows to self.name field."""
        source = """\
class Dog:
    def set_name(self, name):
        self.name = name

d = Dog()
d.set_name("Rex")
"""
        result = _analyze_source(source, Language.PYTHON)
        flows = _extract_summary_flows(result, "set_name")
        field_flows = [
            (src, dst)
            for src, dst in flows
            if isinstance(src, VariableEndpoint) and isinstance(dst, FieldEndpoint)
        ]
        assert len(field_flows) >= 1
        src, dst = field_flows[0]
        assert src.name == "name"
        assert dst.field == "name"


class TestParamToReturnFlowsJavaScript:
    """Assert specific param→return flows from real JavaScript programs."""

    def test_js_identity_param_flows_to_return(self):
        """function f(x) { return x; } → x flows to return."""
        result = _analyze_source(
            "function f(x) { return x; }\nf(1);\n", Language.JAVASCRIPT
        )
        flows = _extract_summary_flows(result, "f")
        param_to_return = [
            (src, dst)
            for src, dst in flows
            if isinstance(src, VariableEndpoint) and isinstance(dst, ReturnEndpoint)
        ]
        assert len(param_to_return) == 1
        assert param_to_return[0][0].name == "x"

    def test_js_computation_param_flows_to_return(self):
        """function double(n) { return n * 2; } → n flows to return."""
        result = _analyze_source(
            "function double(n) { return n * 2; }\ndouble(5);\n",
            Language.JAVASCRIPT,
        )
        flows = _extract_summary_flows(result, "double")
        param_names = {
            src.name
            for src, dst in flows
            if isinstance(src, VariableEndpoint) and isinstance(dst, ReturnEndpoint)
        }
        assert "n" in param_names


class TestParamToReturnFlowsRust:
    """Assert specific param→return flows from real Rust programs."""

    def test_rust_identity_param_flows_to_return(self):
        """fn id(x: i32) -> i32 { x } → x flows to return."""
        result = _analyze_source(
            "fn id(x: i32) -> i32 { x }\nlet r = id(1);\n", Language.RUST
        )
        # Filter precisely — Rust prelude (Box) adds extra summaries
        flows = [
            (src, dst)
            for key, summary in result.summaries.items()
            if key.function.label.startswith("func_id_")
            for src, dst in summary.flows
            if isinstance(src, VariableEndpoint) and isinstance(dst, ReturnEndpoint)
        ]
        assert len(flows) == 1
        assert flows[0][0].name == "x"

    def test_rust_computation_param_flows_to_return(self):
        """fn add(a: i32, b: i32) -> i32 { a + b } → both a, b flow to return."""
        result = _analyze_source(
            "fn add(a: i32, b: i32) -> i32 { a + b }\nlet r = add(1, 2);\n",
            Language.RUST,
        )
        param_names = {
            src.name
            for key, summary in result.summaries.items()
            if key.function.label.startswith("func_add_")
            for src, dst in summary.flows
            if isinstance(src, VariableEndpoint) and isinstance(dst, ReturnEndpoint)
        }
        assert param_names == {"a", "b"}
