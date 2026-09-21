# pyright: standard
"""The one place a COBOL program's return to its caller is emitted.

``GOBACK``, ``EXIT PROGRAM`` and running off the end of the PROCEDURE DIVISION are
three spellings of the same event, so they share one emitter. ``STOP RUN`` is not
among them: it ends the run unit rather than returning, and lowers to ``Halt_``.

Kept in its own module so ``lower_procedure`` can reach it without importing
``lower_arithmetic`` (which imports the procedure lowering back).
"""

from __future__ import annotations

from cobol_asg.source_span import SourceSpan
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.instructions import Const, Return_


def lower_program_exit(
    ctx: EmitContext,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None,
) -> None:
    """Emit the return that hands control back to this program's caller."""
    value_reg = ctx.fresh_reg()
    ctx.emit_inst(Const.int_(value_reg, 0), span=span)
    ctx.emit_inst(Return_(value_reg=value_reg), span=span)
