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
