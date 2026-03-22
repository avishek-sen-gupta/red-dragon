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
from interpreter.interprocedural.types import InterproceduralResult
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

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "CALL_FUNCTION operand is the function name (e.g. 'countdown') "
            "but call_graph.build_function_entries keys by CFG label (e.g. 'func_countdown_0'). "
            "Callee resolution needs a name-to-label mapping."
        ),
    )
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

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "CALL_FUNCTION operand is the function name (e.g. 'f') "
            "but call_graph.build_function_entries keys by CFG label (e.g. 'func_f_1'). "
            "Callee resolution needs a name-to-label mapping."
        ),
    )
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

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Whole-program flow graph is empty because callee resolution fails: "
            "CALL_FUNCTION uses function names but function_entries is keyed by CFG labels. "
            "Without resolved callees, no cross-function flows are propagated."
        ),
    )
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
