"""Unit tests for C# P0 gaps: throw_expression, goto_statement, labeled_statement."""

from __future__ import annotations

from interpreter.frontends.csharp import CSharpFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _parse_csharp(source: str) -> list[IRInstruction]:
    frontend = CSharpFrontend(TreeSitterParserFactory(), "csharp")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


# ── throw_expression ──────────────────────────────────────────────


class TestCSharpThrowExpression:
    """C# throw as an expression: x ?? throw new Exception()."""

    def test_throw_expression_no_unsupported_symbolic(self):
        """throw_expression should not produce unsupported SYMBOLIC."""
        source = """\
string name = null;
string result = name ?? throw new ArgumentNullException("name");
"""
        instructions = _parse_csharp(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any(
            "unsupported:" in str(inst.operands) for inst in symbolics
        ), f"Found unsupported: {[s for s in symbolics if 'unsupported:' in str(s.operands)]}"

    def test_throw_expression_emits_throw(self):
        """throw_expression should emit a THROW opcode."""
        source = """\
string name = null;
string result = name ?? throw new ArgumentNullException("name");
"""
        instructions = _parse_csharp(source)
        throws = _find_all(instructions, Opcode.THROW)
        assert len(throws) >= 1, "throw expression should emit THROW"


# ── goto_statement ────────────────────────────────────────────────


class TestCSharpGotoStatement:
    """C# goto statement: goto label;"""

    def test_goto_no_unsupported_symbolic(self):
        """goto_statement should not produce unsupported SYMBOLIC."""
        source = """\
int x = 1;
goto skip;
x = 99;
skip:
int y = 2;
"""
        instructions = _parse_csharp(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_goto_emits_branch(self):
        """goto should emit a BRANCH to the target label."""
        source = """\
int x = 1;
goto skip;
x = 99;
skip:
int y = 2;
"""
        instructions = _parse_csharp(source)
        branches = _find_all(instructions, Opcode.BRANCH)
        assert any(
            "skip" in inst.label.value for inst in branches
        ), "goto should emit BRANCH to 'skip'"


# ── labeled_statement ─────────────────────────────────────────────


class TestCSharpLabeledStatement:
    """C# labeled statements: label: statement."""

    def test_labeled_statement_no_unsupported_symbolic(self):
        """labeled_statement should not produce unsupported SYMBOLIC."""
        source = """\
int x = 1;
myLabel:
int y = 2;
"""
        instructions = _parse_csharp(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_labeled_statement_emits_label(self):
        """labeled_statement should emit a LABEL opcode."""
        source = """\
int x = 1;
myLabel:
int y = 2;
"""
        instructions = _parse_csharp(source)
        labels = _find_all(instructions, Opcode.LABEL)
        assert any(
            "myLabel" in inst.label.value for inst in labels
        ), "labeled_statement should emit LABEL 'myLabel'"

    def test_labeled_statement_lowers_body(self):
        """The statement after the label should be lowered."""
        source = """\
int x = 1;
myLabel:
int y = x + 1;
"""
        instructions = _parse_csharp(source)
        stores = _find_all(instructions, Opcode.DECL_VAR)
        var_names = [inst.operands[0] for inst in stores]
        assert "y" in var_names, "Statement after label should be lowered"
