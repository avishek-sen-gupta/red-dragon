"""Statement dispatch — routes COBOL statements to their lowering functions."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_statements import (
    AcceptStatement,
    AlterStatement,
    ArithmeticCorrespondingStatement,
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
    ExitProgramStatement,
    ExitStatement,
    GobackStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    InspectStatement,
    MoveCorrespondingStatement,
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
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.lower_arithmetic import (
    lower_arithmetic,
    lower_arithmetic_corresponding,
    lower_compute,
    lower_continue,
    lower_display,
    lower_evaluate,
    lower_exit,
    lower_exit_program,
    lower_goback,
    lower_goto,
    lower_if,
    lower_initialize,
    lower_move,
    lower_move_corresponding,
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
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Route a COBOL statement to its lowering function."""
    if isinstance(stmt, MoveStatement):
        lower_move(ctx, stmt, materialised)
    elif isinstance(stmt, MoveCorrespondingStatement):
        # MoveCorrespondingStatement still uses (layout, region_reg) — uses first WS section
        ws_layout, ws_reg = materialised.working_storage
        lower_move_corresponding(ctx, stmt, ws_layout, ws_reg)
    elif isinstance(stmt, ArithmeticCorrespondingStatement):
        lower_arithmetic_corresponding(ctx, stmt, materialised)
    elif isinstance(stmt, ArithmeticStatement):
        lower_arithmetic(ctx, stmt, materialised)
    elif isinstance(stmt, ComputeStatement):
        lower_compute(ctx, stmt, materialised)
    elif isinstance(stmt, IfStatement):
        lower_if(ctx, stmt, materialised)
    elif isinstance(stmt, PerformStatement):
        lower_perform(ctx, stmt, materialised)
    elif isinstance(stmt, DisplayStatement):
        lower_display(ctx, stmt, materialised)
    elif isinstance(stmt, StopRunStatement):
        lower_stop_run(ctx, stmt, materialised)
    elif isinstance(stmt, GobackStatement):
        lower_goback(ctx, stmt, materialised)
    elif isinstance(stmt, ExitProgramStatement):
        lower_exit_program(ctx, stmt, materialised)
    elif isinstance(stmt, GotoStatement):
        lower_goto(ctx, stmt, materialised)
    elif isinstance(stmt, EvaluateStatement):
        lower_evaluate(ctx, stmt, materialised)
    elif isinstance(stmt, ContinueStatement):
        lower_continue(ctx, stmt, materialised)
    elif isinstance(stmt, ExitStatement):
        lower_exit(ctx, stmt, materialised)
    elif isinstance(stmt, InitializeStatement):
        lower_initialize(ctx, stmt, materialised)
    elif isinstance(stmt, SetStatement):
        lower_set(ctx, stmt, materialised)
    elif isinstance(stmt, StringStatement):
        lower_string(ctx, stmt, materialised)
    elif isinstance(stmt, UnstringStatement):
        lower_unstring(ctx, stmt, materialised)
    elif isinstance(stmt, InspectStatement):
        lower_inspect(ctx, stmt, materialised)
    elif isinstance(stmt, SearchStatement):
        lower_search(ctx, stmt, materialised)
    elif isinstance(stmt, CallStatement):
        lower_call(ctx, stmt, materialised)
    elif isinstance(stmt, AlterStatement):
        lower_alter(ctx, stmt, materialised)
    elif isinstance(stmt, EntryStatement):
        lower_entry(ctx, stmt, materialised)
    elif isinstance(stmt, CancelStatement):
        lower_cancel(ctx, stmt, materialised)
    elif isinstance(stmt, AcceptStatement):
        lower_accept(ctx, stmt, materialised)
    elif isinstance(stmt, OpenStatement):
        lower_open(ctx, stmt, materialised)
    elif isinstance(stmt, CloseStatement):
        lower_close(ctx, stmt, materialised)
    elif isinstance(stmt, ReadStatement):
        lower_read(ctx, stmt, materialised)
    elif isinstance(stmt, WriteStatement):
        lower_write(ctx, stmt, materialised)
    elif isinstance(stmt, RewriteStatement):
        lower_rewrite(ctx, stmt, materialised)
    elif isinstance(stmt, StartStatement):
        lower_start(ctx, stmt, materialised)
    elif isinstance(stmt, DeleteStatement):
        lower_delete(ctx, stmt, materialised)
    # ── Extension statements (EXEC CICS / EXEC SQL / …) routed via the array ──
    else:
        for strat in ctx.extension_strategies:
            if strat.handles(stmt):
                strat.lower(ctx, stmt, materialised)
                return
        logger.warning("Unhandled COBOL statement type: %s", type(stmt).__name__)
