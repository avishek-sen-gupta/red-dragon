"""Tests for CFG builder and Mermaid export."""

from interpreter.cfg import build_cfg, cfg_to_mermaid, CFG, BasicBlock
from interpreter.ir import IRInstruction, Opcode


def _make_instructions(*specs):
    """Helper: build IRInstruction list from (opcode, kwargs) tuples."""
    return [IRInstruction(opcode=op, **kw) for op, kw in specs]


class TestCfgToMermaidBasic:
    def test_linear_cfg_has_flowchart_header(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [42]}),
            (Opcode.STORE_VAR, {"operands": ["x", "t0"]}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert mermaid.startswith("flowchart TD")

    def test_linear_cfg_contains_node_and_instructions(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [42]}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "<b>entry</b>" in mermaid
        assert "t0 = const 42" in mermaid
        assert "return t0" in mermaid

    def test_linear_cfg_has_entry_style(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "style entry fill:#28a745,color:#fff" in mermaid

    def test_fallthrough_edge(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "block_a"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [1]}),
            (Opcode.LABEL, {"label": "block_b"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "block_a --> block_b" in mermaid


class TestCfgToMermaidBranch:
    def test_branch_if_produces_true_false_labels(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [True]}),
            (Opcode.BRANCH_IF, {"operands": ["t0"], "label": "then_block, else_block"}),
            (Opcode.LABEL, {"label": "then_block"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
            (Opcode.LABEL, {"label": "else_block"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert '-->|"T"|' in mermaid
        assert '-->|"F"|' in mermaid
        assert "then_block" in mermaid
        assert "else_block" in mermaid

    def test_unconditional_branch_has_no_label(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.BRANCH, {"label": "target"}),
            (Opcode.LABEL, {"label": "target"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "entry --> target" in mermaid
        assert '-->|"T"|' not in mermaid


class TestCfgToMermaidEscaping:
    def test_quotes_in_operands_are_escaped(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": ['"hello"']}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        # Raw quotes must not appear inside node labels
        assert '"hello"' not in mermaid.split("\n", 1)[1]
        assert "#quot;hello#quot;" in mermaid

    def test_angle_brackets_are_escaped_in_instructions(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": ["<value>"]}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        # The bold tag <b> is intentional Mermaid HTML, but user data must be escaped
        content_lines = [ln for ln in mermaid.split("\n") if "t0 = const" in ln]
        assert len(content_lines) == 1
        assert "#lt;value#gt;" in content_lines[0]


class TestCfgToMermaidSubgraphs:
    def test_function_blocks_grouped_in_subgraph(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [1]}),
            (Opcode.LABEL, {"label": "func_foo_0"}),
            (Opcode.CONST, {"result_reg": "t1", "operands": [2]}),
            (Opcode.BRANCH, {"label": "end_foo_0"}),
            (Opcode.LABEL, {"label": "end_foo_0"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert 'subgraph fn_foo["fn foo"]' in mermaid
        # func_foo_0 node should be inside the subgraph (indented 8 spaces)
        mermaid_lines = mermaid.split("\n")
        func_node_lines = [
            ln for ln in mermaid_lines if "func_foo_0" in ln and '["' in ln
        ]
        assert len(func_node_lines) == 1
        assert func_node_lines[0].startswith("        ")

    def test_class_blocks_grouped_in_subgraph(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [1]}),
            (Opcode.LABEL, {"label": "class_Bar_0"}),
            (Opcode.CONST, {"result_reg": "t1", "operands": [1]}),
            (Opcode.LABEL, {"label": "end_class_Bar_0"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert 'subgraph class_Bar["class Bar"]' in mermaid

    def test_toplevel_blocks_outside_subgraph(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [1]}),
            (Opcode.LABEL, {"label": "func_foo_0"}),
            (Opcode.BRANCH, {"label": "end_foo_0"}),
            (Opcode.LABEL, {"label": "end_foo_0"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)
        mermaid_lines = mermaid.split("\n")

        # entry should be top-level (indented 4 spaces, not 8); uses stadium shape
        entry_lines = [ln for ln in mermaid_lines if "entry" in ln and "([" in ln]
        assert any(
            ln.startswith("    ") and not ln.startswith("        ")
            for ln in entry_lines
        )

    def test_mismatched_counters_still_grouped(self):
        """func_foo_0 pairs with end_foo_1 (counters differ)."""
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [1]}),
            (Opcode.LABEL, {"label": "func_foo_0"}),
            (Opcode.CONST, {"result_reg": "t1", "operands": [2]}),
            (Opcode.BRANCH, {"label": "end_foo_1"}),
            (Opcode.LABEL, {"label": "end_foo_1"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert 'subgraph fn_foo["fn foo"]' in mermaid
        # func_foo_0 should be inside the subgraph
        mermaid_lines = mermaid.split("\n")
        func_node_lines = [
            ln for ln in mermaid_lines if "func_foo_0" in ln and '["' in ln
        ]
        assert len(func_node_lines) == 1
        assert func_node_lines[0].startswith("        ")

    def test_no_subgraph_when_no_functions(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "subgraph" not in mermaid


class TestCfgToMermaidPruning:
    def test_unreachable_blocks_excluded(self):
        """Blocks with no path from entry should not appear in output."""
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
            (Opcode.LABEL, {"label": "dead_block"}),
            (Opcode.CONST, {"result_reg": "t1", "operands": [99]}),
            (Opcode.RETURN, {"operands": ["t1"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "entry" in mermaid
        assert "dead_block" not in mermaid

    def test_reachable_blocks_retained(self):
        """All blocks reachable from entry should appear."""
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.BRANCH, {"label": "target"}),
            (Opcode.LABEL, {"label": "target"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "entry" in mermaid
        assert "target" in mermaid


def _node_def_lines(mermaid: str, node_id: str) -> list[str]:
    """Extract node definition lines (not edges) for a given node ID."""
    return [
        ln
        for ln in mermaid.split("\n")
        if ln.strip().startswith(node_id) and "-->" not in ln and "style " not in ln
    ]


class TestCfgToMermaidShapes:
    def test_entry_block_uses_stadium_shape(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [1]}),
            (Opcode.LABEL, {"label": "next"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        entry_lines = _node_def_lines(mermaid, "entry")
        assert len(entry_lines) == 1
        assert '(["' in entry_lines[0] and '"])' in entry_lines[0]

    def test_branch_if_block_uses_diamond_shape(self):
        """Entry block ending with BRANCH_IF still gets stadium (entry wins)."""
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [True]}),
            (Opcode.BRANCH_IF, {"operands": ["t0"], "label": "yes, no"}),
            (Opcode.LABEL, {"label": "yes"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
            (Opcode.LABEL, {"label": "no"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        entry_lines = _node_def_lines(mermaid, "entry")
        assert len(entry_lines) == 1
        assert '(["' in entry_lines[0]

    def test_non_entry_branch_if_uses_diamond(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [True]}),
            (Opcode.LABEL, {"label": "check"}),
            (Opcode.BRANCH_IF, {"operands": ["t0"], "label": "yes, no"}),
            (Opcode.LABEL, {"label": "yes"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
            (Opcode.LABEL, {"label": "no"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        check_lines = _node_def_lines(mermaid, "check")
        assert len(check_lines) == 1
        assert '{"' in check_lines[0] and '"}' in check_lines[0]

    def test_return_block_uses_stadium_shape(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [1]}),
            (Opcode.LABEL, {"label": "exit"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        exit_lines = _node_def_lines(mermaid, "exit")
        assert len(exit_lines) == 1
        assert '(["' in exit_lines[0] and '"])' in exit_lines[0]

    def test_regular_block_uses_rectangle_shape(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CONST, {"result_reg": "t0", "operands": [1]}),
            (Opcode.LABEL, {"label": "middle"}),
            (Opcode.CONST, {"result_reg": "t1", "operands": [2]}),
            (Opcode.LABEL, {"label": "end"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        middle_lines = _node_def_lines(mermaid, "middle")
        assert len(middle_lines) == 1
        assert '["' in middle_lines[0]
        # Should NOT be stadium or diamond
        assert '(["' not in middle_lines[0]
        assert '{"' not in middle_lines[0]


class TestCfgToMermaidCallEdges:
    def test_function_body_visible_as_root(self):
        """Function entry blocks are BFS roots and appear in output."""
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.BRANCH, {"label": "end_foo_0"}),
            (Opcode.LABEL, {"label": "func_foo_0"}),
            (Opcode.CONST, {"result_reg": "t1", "operands": [42]}),
            (Opcode.RETURN, {"operands": ["t1"]}),
            (Opcode.LABEL, {"label": "end_foo_0"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "func_foo_0" in mermaid
        assert "t1 = const 42" in mermaid

    def test_uncalled_function_still_visible(self):
        """Functions with no callers still appear (they're roots)."""
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.BRANCH, {"label": "end_bar_0"}),
            (Opcode.LABEL, {"label": "func_bar_0"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
            (Opcode.LABEL, {"label": "end_bar_0"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "func_bar_0" in mermaid

    def test_call_function_produces_dashed_edge(self):
        """CALL_FUNCTION emits a dashed edge to the function entry block."""
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.CALL_FUNCTION, {"result_reg": "t1", "operands": ["foo", "t0"]}),
            (Opcode.BRANCH, {"label": "end_foo_0"}),
            (Opcode.LABEL, {"label": "func_foo_0"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
            (Opcode.LABEL, {"label": "end_foo_0"}),
            (Opcode.RETURN, {"operands": ["t1"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert '-.->|"call"|' in mermaid
        assert "func_foo_0" in mermaid

    def test_call_function_no_edge_for_unknown_target(self):
        """CALL_FUNCTION with no matching func_ label emits no dashed edge."""
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (
                Opcode.CALL_FUNCTION,
                {"result_reg": "t1", "operands": ["unknown_fn", "t0"]},
            ),
            (Opcode.RETURN, {"operands": ["t1"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "-.->|" not in mermaid

    def test_non_func_dead_block_still_pruned(self):
        """Non-function unreachable blocks remain pruned."""
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": "entry"}),
            (Opcode.RETURN, {"operands": ["t0"]}),
            (Opcode.LABEL, {"label": "dead_block"}),
            (Opcode.RETURN, {"operands": ["t1"]}),
        )
        cfg = build_cfg(instructions)
        mermaid = cfg_to_mermaid(cfg)

        assert "dead_block" not in mermaid
