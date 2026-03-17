"""Unit tests for default parameter shared IR infrastructure."""

from __future__ import annotations

from interpreter.frontends.common.default_params import (
    emit_resolve_default_func,
)
from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.constants import Language
from interpreter.ir import Opcode


def _make_ctx() -> TreeSitterEmitContext:
    """Create a minimal TreeSitterEmitContext for testing."""
    return TreeSitterEmitContext(
        source=b"",
        language=Language.PYTHON,
        observer=NullFrontendObserver(),
        constants=GrammarConstants(),
    )


class TestEmitResolveDefaultFunc:
    """Tests for emit_resolve_default_func."""

    def test_emits_function_with_correct_label(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        labels = [i for i in ctx.instructions if i.opcode == Opcode.LABEL]
        func_labels = [
            l for l in labels if "func___resolve_default__" in (l.label or "")
        ]
        assert len(func_labels) == 1, f"Expected 1 func label, got {func_labels}"

    def test_emits_three_symbolic_params(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        symbolics = [i for i in ctx.instructions if i.opcode == Opcode.SYMBOLIC]
        param_names = [s.operands[0] for s in symbolics]
        assert "param:arguments_arr" in param_names
        assert "param:param_index" in param_names
        assert "param:default_value" in param_names

    def test_emits_branch_if_for_length_check(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        branch_ifs = [i for i in ctx.instructions if i.opcode == Opcode.BRANCH_IF]
        assert len(branch_ifs) == 1

    def test_emits_func_ref_in_symbol_table(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        func_refs = [
            ref
            for ref in ctx.func_symbol_table.values()
            if ref.name == "__resolve_default__"
        ]
        assert len(func_refs) == 1

    def test_idempotent_on_second_call(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        count_1 = len(ctx.instructions)
        emit_resolve_default_func(ctx)
        count_2 = len(ctx.instructions)
        assert count_1 == count_2, "Second call should be a no-op"

    def test_sets_emitted_flag(self):
        ctx = _make_ctx()
        assert ctx._resolve_default_emitted is False
        emit_resolve_default_func(ctx)
        assert ctx._resolve_default_emitted is True
