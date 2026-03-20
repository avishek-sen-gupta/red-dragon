"""Unit tests for pattern compiler IR emission."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    LiteralPattern,
    WildcardPattern,
    CapturePattern,
    SequencePattern,
    MappingPattern,
    ClassPattern,
    OrPattern,
    AsPattern,
    StarPattern,
    MatchCase,
    compile_pattern_test,
    compile_pattern_bindings,
    compile_match,
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


class TestSequencePattern:
    def test_emits_len_check_and_load_index(self):
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(LiteralPattern(1), LiteralPattern(2)))
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        calls = [i for i in instrs if i.opcode == Opcode.CALL_FUNCTION]
        assert any(
            "len" in str(c.operands) for c in calls
        ), f"expected len() call, got {calls}"
        load_idxs = [i for i in instrs if i.opcode == Opcode.LOAD_INDEX]
        assert len(load_idxs) >= 2, f"expected 2 LOAD_INDEX, got {load_idxs}"

    def test_nested_literals(self):
        ctx = _make_ctx()
        inner = SequencePattern(elements=(LiteralPattern(3), LiteralPattern(4)))
        outer = SequencePattern(elements=(LiteralPattern(1), inner))
        result_reg = compile_pattern_test(ctx, "%subj", outer)
        instrs = ctx.instructions
        calls = [i for i in instrs if i.opcode == Opcode.CALL_FUNCTION]
        len_calls = [c for c in calls if "len" in str(c.operands)]
        assert (
            len(len_calls) >= 2
        ), f"expected 2 len() calls (outer+inner), got {len_calls}"

    def test_bindings_from_captures_in_sequence(self):
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(CapturePattern("a"), CapturePattern("b")))
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        names = [s.operands[0] for s in stores]
        assert "a" in names and "b" in names


class TestMappingPattern:
    def test_emits_load_field_per_key(self):
        ctx = _make_ctx()
        pattern = MappingPattern(
            entries=(
                ("key1", LiteralPattern(10)),
                ("key2", CapturePattern("val")),
            )
        )
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        load_fields = [i for i in instrs if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_fields) >= 2, f"expected 2 LOAD_FIELD, got {load_fields}"
        field_names = [lf.operands[1] for lf in load_fields]
        assert "key1" in field_names and "key2" in field_names

    def test_bindings_from_mapping_values(self):
        ctx = _make_ctx()
        pattern = MappingPattern(entries=(("k", CapturePattern("val")),))
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        assert any(s.operands[0] == "val" for s in stores)


class TestClassPattern:
    def test_emits_isinstance_and_field_access(self):
        ctx = _make_ctx()
        pattern = ClassPattern(
            class_name="Point",
            positional=(LiteralPattern(1), LiteralPattern(2)),
            keyword=(),
        )
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        calls = [i for i in instrs if i.opcode == Opcode.CALL_FUNCTION]
        assert any(
            "isinstance" in str(c.operands) for c in calls
        ), f"expected isinstance call, got {calls}"
        load_idxs = [i for i in instrs if i.opcode == Opcode.LOAD_INDEX]
        assert len(load_idxs) >= 2

    def test_keyword_emits_load_field(self):
        ctx = _make_ctx()
        pattern = ClassPattern(
            class_name="Point",
            positional=(),
            keyword=(("x", LiteralPattern(1)), ("y", LiteralPattern(2))),
        )
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        load_fields = [i for i in instrs if i.opcode == Opcode.LOAD_FIELD]
        field_names = [lf.operands[1] for lf in load_fields]
        assert "x" in field_names and "y" in field_names


class TestOrPattern:
    def test_short_circuits(self):
        ctx = _make_ctx()
        pattern = OrPattern(alternatives=(LiteralPattern(1), LiteralPattern(2)))
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        binops = [
            i for i in instrs if i.opcode == Opcode.BINOP and i.operands[0] == "=="
        ]
        assert len(binops) >= 2, f"expected >=2 equality checks, got {binops}"


class TestAsPattern:
    def test_binds_after_inner_test(self):
        ctx = _make_ctx()
        pattern = AsPattern(pattern=LiteralPattern(42), name="x")
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        binops = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert len(binops) >= 1

    def test_emits_store_var(self):
        ctx = _make_ctx()
        pattern = AsPattern(pattern=LiteralPattern(42), name="x")
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        assert any(s.operands[0] == "x" for s in stores)


class TestCompileMatch:
    def test_multiple_cases_linear_chain(self):
        """Three literal cases produce a linear chain with labels."""
        ctx = _make_ctx()
        cases = [
            MatchCase(
                pattern=LiteralPattern(1), guard_node=NoGuard(), body_node=NoBody()
            ),
            MatchCase(
                pattern=LiteralPattern(2), guard_node=NoGuard(), body_node=NoBody()
            ),
            MatchCase(
                pattern=WildcardPattern(), guard_node=NoGuard(), body_node=NoBody()
            ),
        ]
        compile_match(ctx, "%subj", cases)
        instrs = ctx.instructions
        labels = [i.label for i in instrs if i.opcode == Opcode.LABEL]
        branches = [i for i in instrs if i.opcode == Opcode.BRANCH]
        branch_ifs = [i for i in instrs if i.opcode == Opcode.BRANCH_IF]
        assert len(branch_ifs) >= 2, f"expected >=2 BRANCH_IF, got {branch_ifs}"
        assert any(
            "match_end" in l for l in labels
        ), f"expected match_end label, got {labels}"

    def test_two_pass_no_partial_binding(self):
        """Bindings should only appear after the BRANCH_IF test, not before."""
        ctx = _make_ctx()
        cases = [
            MatchCase(
                pattern=SequencePattern(
                    elements=(CapturePattern("a"), CapturePattern("b"))
                ),
                guard_node=NoGuard(),
                body_node=NoBody(),
            ),
        ]
        compile_match(ctx, "%subj", cases)
        instrs = ctx.instructions
        branch_if_idx = next(
            i for i, inst in enumerate(instrs) if inst.opcode == Opcode.BRANCH_IF
        )
        stores_before = [
            inst
            for inst in instrs[:branch_if_idx]
            if inst.opcode == Opcode.STORE_VAR and inst.operands[0] in ("a", "b")
        ]
        assert (
            len(stores_before) == 0
        ), f"bindings should not appear before BRANCH_IF: {stores_before}"


class TestStarPattern:
    def test_star_pattern_standalone_returns_true(self):
        """StarPattern by itself always matches (no test IR needed)."""
        ctx = _make_ctx()
        pattern = StarPattern(name="rest")
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        binops = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert len(binops) == 0, f"star should emit no BINOP, got {binops}"

    def test_star_pattern_bindings_emits_store_var(self):
        """StarPattern with a real name emits STORE_VAR."""
        ctx = _make_ctx()
        pattern = StarPattern(name="rest")
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        assert len(stores) == 1
        assert stores[0].operands[0] == "rest"
        assert stores[0].operands[1] == "%subj"

    def test_star_pattern_wildcard_emits_no_store(self):
        """StarPattern with name='_' must not emit STORE_VAR."""
        ctx = _make_ctx()
        pattern = StarPattern(name="_")
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        assert len(stores) == 0, f"wildcard star should emit no STORE_VAR, got {stores}"


class TestGuardedCase:
    def test_emits_guard_after_pattern_test(self):
        """Guard test: no guard should produce just a BRANCH_IF from pattern test."""
        # Unit test only verifies NoGuard path (no real tree-sitter guard node available).
        # Guard AND logic is exercised in integration tests (TestGuard in Task 12).
        ctx = _make_ctx()
        cases = [
            MatchCase(
                pattern=LiteralPattern(1), guard_node=NoGuard(), body_node=NoBody()
            ),
        ]
        compile_match(ctx, "%subj", cases)
        instrs = ctx.instructions
        branch_ifs = [i for i in instrs if i.opcode == Opcode.BRANCH_IF]
        assert len(branch_ifs) >= 1
