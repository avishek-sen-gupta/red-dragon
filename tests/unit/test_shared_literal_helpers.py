"""Unit tests for shared typed literal/ref emission helpers in common/expressions.py.

Tests are written TDD-style: they define the desired API and fail until the
helpers are implemented.

Convention (documented here for all per-frontend stories to follow):
  - `lower_int_literal(ctx, node, *, text=None)` — parse int with base + separator
    handling, emit Const.int_.
  - `lower_float_literal(ctx, node, *, text=None)` — emit Const.float_.
  - `lower_string_literal(ctx, node, value)` — `value` is already-unquoted str,
    emit Const.string.  Per-language unquoting stays in the frontend story.
  - `lower_null_literal(ctx, node)` — emit Const.null_.
  - `lower_bool_literal(ctx, node, value)` — emit Const.bool_(reg, bool(value)).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from interpreter.constants import FoundationTypeName
from interpreter.instructions import Const
from interpreter.ir import Opcode
from interpreter.register import Register
from interpreter.types.type_expr import NULL, scalar
from tests.covers import NotLanguageFeature, covers

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_ctx(node_text: str = "") -> MagicMock:
    """Return a minimal mock TreeSitterEmitContext."""
    ctx = MagicMock()
    ctx.fresh_reg.side_effect = _reg_factory()
    ctx.node_text.return_value = node_text
    # Capture emitted instructions
    ctx._emitted: list[Const] = []
    ctx.emit_inst.side_effect = lambda inst, **_: ctx._emitted.append(inst)
    return ctx


_reg_counter = 0


def _reg_factory():
    def _next():
        global _reg_counter
        r = Register(f"%{_reg_counter}")
        _reg_counter += 1
        return r

    return _next


def _last_const(ctx: MagicMock) -> Const:
    consts = [i for i in ctx._emitted if isinstance(i, Const)]
    assert consts, "No CONST instruction was emitted"
    return consts[-1]


# ── tests: lower_int_literal ─────────────────────────────────────────────────


class TestLowerIntLiteral:
    """lower_int_literal(ctx, node, *, text=None) → Register.

    Parses int with base handling and digit-separator stripping.
    """

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_decimal_integer(self):
        from interpreter.frontends.common.expressions import lower_int_literal

        ctx = _make_ctx("42")
        reg = lower_int_literal(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.opcode == Opcode.CONST
        assert inst.value == 42
        assert inst.type_expr == scalar(FoundationTypeName.INT)
        assert reg == inst.result_reg

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_hex_integer(self):
        from interpreter.frontends.common.expressions import lower_int_literal

        ctx = _make_ctx("0xFF")
        reg = lower_int_literal(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.value == 255

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_binary_integer(self):
        from interpreter.frontends.common.expressions import lower_int_literal

        ctx = _make_ctx("0b101")
        lower_int_literal(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.value == 5

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_octal_integer(self):
        from interpreter.frontends.common.expressions import lower_int_literal

        ctx = _make_ctx("0o17")
        lower_int_literal(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.value == 15

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_underscore_separator(self):
        from interpreter.frontends.common.expressions import lower_int_literal

        ctx = _make_ctx("1_000_000")
        lower_int_literal(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.value == 1_000_000

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_text_override_strips_suffix(self):
        """text= param allows callers to pass pre-stripped text (e.g. Java 'L' removed)."""
        from interpreter.frontends.common.expressions import lower_int_literal

        ctx = _make_ctx("99L")  # node text — irrelevant when text= supplied
        lower_int_literal(ctx, MagicMock(), text="99")
        inst = _last_const(ctx)
        assert inst.value == 99

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_tick_separator_stripped(self):
        """C++14 digit separators using apostrophe should be stripped."""
        from interpreter.frontends.common.expressions import lower_int_literal

        ctx = _make_ctx("1'000")
        lower_int_literal(ctx, MagicMock(), text="1000")
        inst = _last_const(ctx)
        assert inst.value == 1000


# ── tests: lower_float_literal ───────────────────────────────────────────────


class TestLowerFloatLiteral:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_simple_float(self):
        from interpreter.frontends.common.expressions import lower_float_literal

        ctx = _make_ctx("3.14")
        reg = lower_float_literal(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.opcode == Opcode.CONST
        assert inst.value == 3.14
        assert inst.type_expr == scalar(FoundationTypeName.FLOAT)
        assert reg == inst.result_reg

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_scientific_notation(self):
        from interpreter.frontends.common.expressions import lower_float_literal

        ctx = _make_ctx("1e10")
        lower_float_literal(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.value == 1e10

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_text_override(self):
        from interpreter.frontends.common.expressions import lower_float_literal

        ctx = _make_ctx("1.5f")
        lower_float_literal(ctx, MagicMock(), text="1.5")
        inst = _last_const(ctx)
        assert inst.value == 1.5


# ── tests: lower_string_literal ──────────────────────────────────────────────


class TestLowerStringLiteral:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_plain_string(self):
        from interpreter.frontends.common.expressions import lower_string_literal

        ctx = _make_ctx('"hello"')
        reg = lower_string_literal(ctx, MagicMock(), "hello")
        inst = _last_const(ctx)
        assert inst.opcode == Opcode.CONST
        assert inst.value == "hello"
        assert inst.type_expr == scalar(FoundationTypeName.STRING)
        assert reg == inst.result_reg

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_empty_string(self):
        from interpreter.frontends.common.expressions import lower_string_literal

        ctx = _make_ctx('""')
        lower_string_literal(ctx, MagicMock(), "")
        inst = _last_const(ctx)
        assert inst.value == ""

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_already_unquoted_value_stored_verbatim(self):
        """The `value` arg is already unquoted; helper stores it as-is."""
        from interpreter.frontends.common.expressions import lower_string_literal

        ctx = _make_ctx("`raw`")
        lower_string_literal(ctx, MagicMock(), "raw")
        inst = _last_const(ctx)
        assert inst.value == "raw"


# ── tests: lower_null_literal ────────────────────────────────────────────────


class TestLowerNullLiteral:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_null(self):
        from interpreter.frontends.common.expressions import lower_null_literal

        ctx = _make_ctx("null")
        reg = lower_null_literal(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.opcode == Opcode.CONST
        assert inst.value is None
        assert inst.type_expr == NULL
        assert reg == inst.result_reg


# ── tests: lower_bool_literal ────────────────────────────────────────────────


class TestLowerBoolLiteral:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_true(self):
        from interpreter.frontends.common.expressions import lower_bool_literal

        ctx = _make_ctx("true")
        reg = lower_bool_literal(ctx, MagicMock(), True)
        inst = _last_const(ctx)
        assert inst.opcode == Opcode.CONST
        assert inst.value is True
        assert inst.type_expr == scalar(FoundationTypeName.BOOL)
        assert reg == inst.result_reg

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_false(self):
        from interpreter.frontends.common.expressions import lower_bool_literal

        ctx = _make_ctx("false")
        lower_bool_literal(ctx, MagicMock(), False)
        inst = _last_const(ctx)
        assert inst.value is False
        assert inst.type_expr == scalar(FoundationTypeName.BOOL)


# ── tests: lower_const_literal raises clearly ─────────────────────────────────


class TestLowerConstLiteralRaises:
    """lower_const_literal must raise TypeError directing callers to typed helpers.

    It cannot be typed without knowing the literal kind, so it is replaced with
    an explicit error rather than silently emitting a wrong type.
    """

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_raises_with_helpful_message(self):
        import pytest

        from interpreter.frontends.common.expressions import lower_const_literal

        ctx = _make_ctx("42")
        with pytest.raises(TypeError, match="typed helper"):
            lower_const_literal(ctx, MagicMock())


# ── tests: canonical helpers in expressions.py ────────────────────────────────


class TestLowerCanonicalNone:
    """lower_canonical_none emits Const.null_."""

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_emits_null(self):
        from interpreter.frontends.common.expressions import lower_canonical_none

        ctx = _make_ctx("None")
        reg = lower_canonical_none(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.value is None
        assert inst.type_expr == NULL
        assert reg == inst.result_reg


class TestLowerCanonicalTrue:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_emits_bool_true(self):
        from interpreter.frontends.common.expressions import lower_canonical_true

        ctx = _make_ctx("True")
        reg = lower_canonical_true(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.value is True
        assert inst.type_expr == scalar(FoundationTypeName.BOOL)


class TestLowerCanonicalFalse:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_emits_bool_false(self):
        from interpreter.frontends.common.expressions import lower_canonical_false

        ctx = _make_ctx("False")
        reg = lower_canonical_false(ctx, MagicMock())
        inst = _last_const(ctx)
        assert inst.value is False
        assert inst.type_expr == scalar(FoundationTypeName.BOOL)


# ── tests: lower_default_return ───────────────────────────────────────────────


class TestLowerDefaultReturn:
    """lower_default_return(ctx, node, sentinel) mirrors _parse_const classification.

    Sentinels:
      - "None" (CanonicalLiteral.NONE) → Const.null_ (value=None, type=NULL)
      - "0"  → Const.int_ (value=0, type=INT scalar)
      - "()" → Const.string (value="()", type=STRING scalar)  — not numeric, stays str
    """

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_none_sentinel_emits_null(self):
        """'None' sentinel → typed null CONST (NULL type_expr, value=None)."""
        from interpreter.constants import CanonicalLiteral
        from interpreter.frontends.common.expressions import lower_default_return

        ctx = _make_ctx()
        reg = lower_default_return(ctx, MagicMock(), CanonicalLiteral.NONE)
        inst = _last_const(ctx)
        assert inst.value is None
        assert inst.type_expr == NULL
        assert reg == inst.result_reg

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_zero_sentinel_emits_int(self):
        """'0' sentinel (C default-return) → typed int CONST with value 0."""
        from interpreter.frontends.common.expressions import lower_default_return

        ctx = _make_ctx()
        reg = lower_default_return(ctx, MagicMock(), "0")
        inst = _last_const(ctx)
        assert inst.value == 0
        assert inst.type_expr == scalar(FoundationTypeName.INT)
        assert reg == inst.result_reg

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_unit_sentinel_emits_string(self):
        """'()' sentinel (Scala/Rust default-return) → typed string CONST with value '()'."""
        from interpreter.frontends.common.expressions import lower_default_return

        ctx = _make_ctx()
        reg = lower_default_return(ctx, MagicMock(), "()")
        inst = _last_const(ctx)
        assert inst.value == "()"
        assert inst.type_expr == scalar(FoundationTypeName.STRING)
        assert reg == inst.result_reg


# ── tests: emit_implicit_return ──────────────────────────────────────────────


class TestEmitImplicitReturn:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_emits_return_marked_implicit(self):
        from interpreter.constants import Language
        from interpreter.frontend_observer import NullFrontendObserver
        from interpreter.frontends.common.declarations import emit_implicit_return
        from interpreter.frontends.context import (
            GrammarConstants,
            TreeSitterEmitContext,
        )
        from interpreter.instructions import Return_
        from interpreter.ir import Opcode

        ctx = TreeSitterEmitContext(
            language=Language.PYTHON,
            source=b"",
            observer=NullFrontendObserver(),
            constants=GrammarConstants(),
        )
        emit_implicit_return(ctx, None)
        returns = [i for i in ctx.instructions if i.opcode == Opcode.RETURN]
        assert len(returns) == 1
        assert isinstance(returns[0], Return_)
        assert returns[0].implicit is True
