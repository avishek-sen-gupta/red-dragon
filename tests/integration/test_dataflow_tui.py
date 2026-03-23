"""Integration tests for dataflow TUI pipeline extension."""

from __future__ import annotations

from interpreter.interprocedural.types import (
    InterproceduralResult,
    ReturnEndpoint,
    VariableEndpoint,
)
from viz.panels.dataflow_graph_panel import (
    ChainNode,
    build_call_chain,
    find_top_level_call_sites,
)
from viz.pipeline import run_pipeline


def _collect_labels(nodes: list[ChainNode]) -> list[str]:
    """Collect all labels from a ChainNode tree."""
    return [lbl for n in nodes for lbl in [n.label] + _collect_labels(n.children)]


def _resolve_callee(callee_label: str, interprocedural):
    """Resolve a callee label to a FunctionEntry (label or name-based)."""
    func_by_label = {f.label: f for f in interprocedural.call_graph.functions}
    entry = func_by_label.get(callee_label)
    if entry:
        return entry
    return next(
        (
            f
            for f in interprocedural.call_graph.functions
            if f.label.startswith("func_")
            and "_" in f.label[5:]
            and f.label.split("_")[1] == callee_label
        ),
        func_by_label.get(callee_label),
    )


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

        func_labels = [l for l in cfg.blocks if l.starts_with("func_f")]
        assert len(func_labels) >= 1
        label = func_labels[0]

        min_line = float("inf")
        max_line = 0
        for block_label, block in cfg.blocks.items():
            if block_label == label or block_label.starts_with(str(label) + "_"):
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


class TestMultiFunctionCallChain:
    """End-to-end: quadruple → double → add call chain with correctness assertions."""

    SOURCE = """\
def add(a, b):
    return a + b

def double(x):
    return add(x, x)

def quadruple(n):
    return double(double(n))

result = quadruple(5)
"""

    def test_top_level_call_is_quadruple(self):
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        top_calls = find_top_level_call_sites(
            result.cfg, result.interprocedural.call_graph
        )
        assert len(top_calls) == 1
        assert "quadruple" in top_calls[0].callee_label
        assert top_calls[0].result_var == "result"

    def test_quadruple_chain_has_correct_structure(self):
        """quadruple(n) should show n flowing into double, then into add."""
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        top_calls = find_top_level_call_sites(
            result.cfg, result.interprocedural.call_graph
        )
        callee = _resolve_callee(top_calls[0].callee_label, result.interprocedural)
        nodes = build_call_chain(
            callee,
            result.interprocedural.call_graph,
            result.interprocedural.summaries,
            result.cfg,
            set(),
        )
        labels = _collect_labels(nodes)

        # n flows to double
        assert any(
            "n" in lbl and "double" in lbl for lbl in labels
        ), f"Expected n → double(...) in chain, got: {labels}"
        # x flows to add
        assert any(
            "x" in lbl and "add" in lbl for lbl in labels
        ), f"Expected x → add(...) in chain, got: {labels}"
        # a and b reach return(add)
        assert any(
            "a" in lbl and "return" in lbl for lbl in labels
        ), f"Expected a → return(add) leaf, got: {labels}"
        assert any(
            "b" in lbl and "return" in lbl for lbl in labels
        ), f"Expected b → return(add) leaf, got: {labels}"
        # n reaches return(quadruple)
        assert any(
            "n" in lbl and "return" in lbl and "quadruple" in lbl for lbl in labels
        ), f"Expected n → return(quadruple) leaf, got: {labels}"

    def test_add_is_leaf_level(self):
        """add(a, b) has no inner calls — its chain nodes should be leaves."""
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        add_entry = next(
            f for f in result.interprocedural.call_graph.functions if "add" in f.label
        )
        nodes = build_call_chain(
            add_entry,
            result.interprocedural.call_graph,
            result.interprocedural.summaries,
            result.cfg,
            set(),
        )
        # All nodes for add should be leaves (no children)
        assert all(
            len(n.children) == 0 for n in nodes
        ), f"add() nodes should be leaves, got children: {[n.label for n in nodes if n.children]}"
        # Should have exactly 2 flows: a→return, b→return
        assert len(nodes) == 2, f"Expected 2 flows for add(a,b), got {len(nodes)}"

    def test_execution_result_matches_dataflow_chain(self):
        """quadruple(5) == 20, AND the dataflow chain traces the correct path.

        Combines runtime execution (via run()) with static dataflow analysis
        (via run_pipeline) to verify both agree.
        """
        from interpreter.run import run

        # Runtime: result == 20 (5 * 2 * 2)
        vm = run(self.SOURCE, language="python")
        runtime_result = vm.current_frame.local_vars["result"]
        assert (
            runtime_result.value == 20
        ), f"Expected quadruple(5) == 20, got {runtime_result.value}"

        # Static: the dataflow chain traces n through double and add
        pipeline = run_pipeline(self.SOURCE, language="python", max_steps=50)
        top_calls = find_top_level_call_sites(
            pipeline.cfg, pipeline.interprocedural.call_graph
        )
        callee = _resolve_callee(top_calls[0].callee_label, pipeline.interprocedural)
        nodes = build_call_chain(
            callee,
            pipeline.interprocedural.call_graph,
            pipeline.interprocedural.summaries,
            pipeline.cfg,
            set(),
        )
        labels = _collect_labels(nodes)

        # The value 5 flows through n → x → a,b → return chain
        assert any("n" in lbl and "double" in lbl for lbl in labels)
        assert any("x" in lbl and "add" in lbl for lbl in labels)
        assert any("a" in lbl and "return" in lbl for lbl in labels)

    def test_chain_node_count(self):
        """The full chain should have 9 nodes (verified from debug output)."""
        result = run_pipeline(self.SOURCE, language="python", max_steps=50)
        top_calls = find_top_level_call_sites(
            result.cfg, result.interprocedural.call_graph
        )
        callee = _resolve_callee(top_calls[0].callee_label, result.interprocedural)
        nodes = build_call_chain(
            callee,
            result.interprocedural.call_graph,
            result.interprocedural.summaries,
            result.cfg,
            set(),
        )
        total = len(_collect_labels(nodes))
        assert total == 9, f"Expected 9 nodes in quadruple chain, got {total}"


class TestIRSourceLocations:
    """All IR instructions should have source location mappings."""

    SOURCE = """\
def add(a, b):
    return a + b

def double(x):
    return add(x, x)

result = double(5)
"""

    def test_all_instructions_have_source_locations(self):
        """Every IR instruction should map back to a source location."""
        from interpreter.cfg import build_cfg
        from interpreter.constants import Language
        from interpreter.frontend import get_frontend

        frontend = get_frontend(Language.PYTHON)
        ir = frontend.lower(self.SOURCE.encode())
        cfg = build_cfg(ir)

        missing = [
            (label, str(inst))
            for label, block in cfg.blocks.items()
            for inst in block.instructions
            if inst.source_location.is_unknown()
        ]
        assert (
            missing == []
        ), f"{len(missing)} instructions missing source locations:\n" + "\n".join(
            f"  {label}: {inst}" for label, inst in missing
        )
