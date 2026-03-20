"""Unit tests for pattern compiler IR emission."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    LiteralPattern,
    WildcardPattern,
    CapturePattern,
    MatchCase,
    compile_pattern_test,
    compile_pattern_bindings,
    NoGuard,
    NoBody,
)
from interpreter.frontends.python import PythonFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.constants import Language


def _make_ctx():
    """Create a minimal TreeSitterEmitContext for testing IR emission."""
    frontend = PythonFrontend(TreeSitterParserFactory(), "python")
    grammar_constants = frontend._build_constants()
    ctx = TreeSitterEmitContext(
        source=b"x = 1",
        language=Language.PYTHON,
        observer=NullFrontendObserver(),
        constants=grammar_constants,
        type_map=frontend._build_type_map(),
        stmt_dispatch=frontend._build_stmt_dispatch(),
        expr_dispatch=frontend._build_expr_dispatch(),
    )
    return ctx


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


class TestLiteralPattern:
    def test_emits_const_and_binop_eq(self):
        ctx = _make_ctx()
        subject_reg = "%subj"
        pattern = LiteralPattern(value=42)
        result_reg = compile_pattern_test(ctx, subject_reg, pattern)
        instrs = ctx.instructions
        consts = [i for i in instrs if i.opcode == Opcode.CONST]
        binops = [i for i in instrs if i.opcode == Opcode.BINOP]
        assert len(consts) >= 1, f"expected CONST, got {_opcodes(instrs)}"
        assert consts[-1].operands == ["42"]
        assert len(binops) >= 1, f"expected BINOP, got {_opcodes(instrs)}"
        assert binops[-1].operands[0] == "=="
        assert binops[-1].operands[1] == subject_reg
        assert result_reg == binops[-1].result_reg

    def test_string_literal_emits_const(self):
        ctx = _make_ctx()
        pattern = LiteralPattern(value="hello")
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        consts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        assert any(c.operands == ['"hello"'] or c.operands == ["hello"] for c in consts)


class TestWildcardPattern:
    def test_emits_no_test(self):
        ctx = _make_ctx()
        pattern = WildcardPattern()
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        binops = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert len(binops) == 0, f"wildcard should emit no BINOP, got {binops}"


class TestCapturePattern:
    def test_emits_no_test(self):
        ctx = _make_ctx()
        pattern = CapturePattern(name="x")
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        binops = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert len(binops) == 0, f"capture should emit no BINOP, got {binops}"

    def test_emits_store_var(self):
        ctx = _make_ctx()
        pattern = CapturePattern(name="x")
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        assert len(stores) >= 1
        assert stores[-1].operands[0] == "x"
        assert stores[-1].operands[1] == "%subj"
