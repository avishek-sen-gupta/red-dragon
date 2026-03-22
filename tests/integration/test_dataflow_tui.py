"""Integration tests for dataflow TUI pipeline extension."""

from __future__ import annotations

from interpreter.interprocedural.types import InterproceduralResult
from viz.pipeline import run_pipeline


class TestPipelineInterproceduralResult:
    SOURCE = """\
def f(x):
    return x + 1

def g(y):
    return f(y) + 2

result = g(10)
"""

    def test_pipeline_result_has_interprocedural_field(self):
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        assert result.interprocedural is not None
        assert isinstance(result.interprocedural, InterproceduralResult)

    def test_interprocedural_has_call_graph(self):
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        assert len(result.interprocedural.call_graph.functions) > 0

    def test_interprocedural_has_summaries(self):
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        assert len(result.interprocedural.summaries) > 0

    def test_interprocedural_has_whole_program_graph(self):
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        assert len(result.interprocedural.whole_program_graph) > 0

    def test_pipeline_no_functions_still_works(self):
        result = run_pipeline("x = 1\ny = x + 1\n", language="python", max_steps=50)
        assert result.interprocedural is not None


class TestDataflowModeToggle:
    """Test mode toggle state transitions."""

    SOURCE = "def f(x):\n    return x + 1\nf(1)\n"

    def test_function_source_span_computation(self):
        """Verify that function block prefix matching finds the right source lines."""
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        cfg = result.cfg

        func_labels = [l for l in cfg.blocks if l.startswith("func_f")]
        assert len(func_labels) >= 1
        label = func_labels[0]

        min_line = float("inf")
        max_line = 0
        for block_label, block in cfg.blocks.items():
            if block_label == label or block_label.startswith(label + "_"):
                for inst in block.instructions:
                    loc = inst.source_location
                    if loc.is_unknown():
                        continue
                    min_line = min(min_line, loc.start_line)
                    max_line = max(max_line, loc.end_line)

        assert max_line > 0, "Should find source lines for function f"
        assert min_line <= 2, "Function f starts at line 1 or 2"


class TestCallChainTreeView:
    SOURCE = """\
def add(a, b):
    return a + b

def double(x):
    return add(x, x)

result = double(5)
"""

    def test_pipeline_produces_nonempty_call_chain(self):
        """The call-chain tree builder produces nodes for a multi-function program."""
        from viz.panels.dataflow_graph_panel import (
            find_top_level_call_sites,
            build_call_chain,
        )

        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        interprocedural = result.interprocedural
        assert interprocedural is not None

        top_calls = find_top_level_call_sites(result.cfg, interprocedural.call_graph)
        assert len(top_calls) >= 1, "Should find top-level call to double()"

        callee_label = top_calls[0].callee_label
        func_by_label = {f.label: f for f in interprocedural.call_graph.functions}
        callee_entry = func_by_label.get(callee_label)
        if callee_entry is None:
            # Name-based fallback
            callee_entry = next(
                (
                    f
                    for f in interprocedural.call_graph.functions
                    if f.label.split("_")[1] == callee_label
                    if f.label.startswith("func_") and "_" in f.label[5:]
                ),
                None,
            )
        assert (
            callee_entry is not None
        ), f"Could not find function entry for {callee_label}"
        nodes = build_call_chain(
            callee_entry,
            interprocedural.call_graph,
            interprocedural.summaries,
            result.cfg,
            set(),
        )
        assert len(nodes) > 0, "Call chain should have at least one node"
