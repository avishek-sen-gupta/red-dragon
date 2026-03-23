"""Unit tests for default parameter shared IR infrastructure."""

from __future__ import annotations

from interpreter.frontends.common.default_params import (
    emit_resolve_default_func,
)
from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.frontends import get_deterministic_frontend
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
            l for l in labels if l.label.contains("func___resolve_default__")
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


def _parse_python(source: str) -> list:
    """Parse Python source and return IR instructions."""
    fe = get_deterministic_frontend(Language.PYTHON)
    return fe.lower(source.encode())


class TestPythonDefaultParamIR:
    """Tests for Python frontend default parameter IR emission."""

    def test_default_param_emits_resolve_call(self):
        """def f(x='hello') should emit CALL_FUNCTION __resolve_default__."""
        instructions = _parse_python("def f(x='hello'):\n    return x\nf()")
        call_fns = [
            i
            for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert (
            len(call_fns) >= 1
        ), "Expected at least 1 CALL_FUNCTION __resolve_default__"

    def test_default_param_emits_store_var(self):
        """Default param guard should reassign the param via STORE_VAR."""
        instructions = _parse_python("def f(x='hello'):\n    return x\nf()")
        store_vars = [
            i
            for i in instructions
            if i.opcode == Opcode.STORE_VAR and i.operands[0] == "x"
        ]
        assert len(store_vars) >= 1, "Expected STORE_VAR x for default resolution"

    def test_typed_default_param_emits_resolve_call(self):
        """def f(x: int = 42) should also emit __resolve_default__."""
        instructions = _parse_python("def f(x: int = 42):\n    return x\nf()")
        call_fns = [
            i
            for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert len(call_fns) >= 1

    def test_required_param_no_resolve(self):
        """def f(x) should NOT emit __resolve_default__."""
        instructions = _parse_python("def f(x):\n    return x\nf('a')")
        call_fns = [
            i
            for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert len(call_fns) == 0

    def test_mixed_params_correct_index(self):
        """def f(a, b='x') — b should get param_index=1."""
        instructions = _parse_python("def f(a, b='x'):\n    return b\nf('a')")
        call_fns = [
            i
            for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert len(call_fns) == 1
        # The param_index constant (1) should appear before the call
        const_1s = [
            i for i in instructions if i.opcode == Opcode.CONST and i.operands == [1]
        ]
        assert len(const_1s) >= 1, "Expected CONST 1 for param_index of b"

    def test_lambda_default_param(self):
        """lambda x='hi': x should emit __resolve_default__."""
        instructions = _parse_python("f = lambda x='hi': x\nf()")
        call_fns = [
            i
            for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert len(call_fns) >= 1
