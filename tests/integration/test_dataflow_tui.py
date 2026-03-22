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
