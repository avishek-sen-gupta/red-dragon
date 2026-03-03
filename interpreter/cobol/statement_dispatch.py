"""Statement dispatch — routes COBOL statements to their lowering functions."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_statements import (
    AcceptStatement,
    AlterStatement,
    ArithmeticStatement,
    CallStatement,
    CancelStatement,
    CloseStatement,
    CobolStatementType,
    ComputeStatement,
    ContinueStatement,
    DisplayStatement,
    EntryStatement,
    EvaluateStatement,
    ExitStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    InspectStatement,
    MoveStatement,
    OpenStatement,
    PerformStatement,
    ReadStatement,
    SearchStatement,
    SetStatement,
    StopRunStatement,
    StringStatement,
    UnstringStatement,
    WriteStatement,
    RewriteStatement,
    StartStatement,
    DeleteStatement,
)
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_arithmetic import (
    lower_arithmetic,
    lower_compute,
    lower_continue,
    lower_display,
    lower_evaluate,
    lower_exit,
    lower_goto,
    lower_if,
    lower_initialize,
    lower_move,
    lower_set,
    lower_stop_run,
)
from interpreter.cobol.lower_call import (
    lower_alter,
    lower_call,
    lower_cancel,
    lower_entry,
)
from interpreter.cobol.lower_io import (
    lower_accept,
    lower_close,
    lower_delete,
    lower_open,
    lower_read,
    lower_rewrite,
    lower_start,
    lower_write,
)
from interpreter.cobol.lower_perform import lower_perform
from interpreter.cobol.lower_search import lower_search
from interpreter.cobol.lower_string_inspect import (
    lower_inspect,
    lower_string,
    lower_unstring,
)

logger = logging.getLogger(__name__)


def dispatch_statement(
    ctx: EmitContext,
    stmt: CobolStatementType,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """Route a COBOL statement to its lowering function."""
    if isinstance(stmt, MoveStatement):
        lower_move(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, ArithmeticStatement):
        lower_arithmetic(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, ComputeStatement):
        lower_compute(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, IfStatement):
        lower_if(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, PerformStatement):
        lower_perform(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, DisplayStatement):
        lower_display(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, StopRunStatement):
        lower_stop_run(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, GotoStatement):
        lower_goto(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, EvaluateStatement):
        lower_evaluate(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, ContinueStatement):
        lower_continue(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, ExitStatement):
        lower_exit(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, InitializeStatement):
        lower_initialize(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, SetStatement):
        lower_set(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, StringStatement):
        lower_string(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, UnstringStatement):
        lower_unstring(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, InspectStatement):
        lower_inspect(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, SearchStatement):
        lower_search(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, CallStatement):
        lower_call(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, AlterStatement):
        lower_alter(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, EntryStatement):
        lower_entry(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, CancelStatement):
        lower_cancel(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, AcceptStatement):
        lower_accept(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, OpenStatement):
        lower_open(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, CloseStatement):
        lower_close(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, ReadStatement):
        lower_read(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, WriteStatement):
        lower_write(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, RewriteStatement):
        lower_rewrite(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, StartStatement):
        lower_start(ctx, stmt, layout, region_reg)
    elif isinstance(stmt, DeleteStatement):
        lower_delete(ctx, stmt, layout, region_reg)
    else:
        logger.warning("Unhandled COBOL statement type: %s", type(stmt).__name__)
