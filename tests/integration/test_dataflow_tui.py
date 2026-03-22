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
