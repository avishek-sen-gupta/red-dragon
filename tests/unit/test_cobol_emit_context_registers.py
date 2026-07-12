"""The COBOL frontend must emit registers named %0, %1, ... (matching the
tree-sitter frontends), not %r0, %r1, .... Divergent naming caused a
cross-module register-collision bug (red-dragon-irl8)."""

from __future__ import annotations

from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.statement_dispatch import dispatch_statement
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fresh_reg_uses_plain_numeric_naming():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    r0 = ctx.fresh_reg()
    r1 = ctx.fresh_reg()
    assert str(r0) == "%0"
    assert str(r1) == "%1"
