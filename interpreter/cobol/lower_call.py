"""CALL, ALTER, ENTRY, CANCEL statement lowering."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_statements import (
    AlterStatement,
    CallStatement,
    CancelStatement,
    EntryStatement,
)
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.var_name import VarName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    CallWithMemory,
    Label_,
    StoreVar,
)
from interpreter.ir import CodeLabel

logger = logging.getLogger(__name__)


def lower_call(
    ctx: EmitContext,
    stmt: CallStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CALL 'program' USING params — region-passing subprogram invocation via CallWithMemory.

    BY REFERENCE (default): passes the caller's WORKING-STORAGE region to the callee
    as both params_reg and results_reg. The callee reads LINKAGE fields from that region.
    """
    ws_layout, ws_reg = materialised.working_storage

    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallWithMemory(
            result_reg=result_reg,
            func_name=FuncName(stmt.program),
            params_reg=ws_reg,
            results_reg=ws_reg,
        )
    )

    if stmt.giving and ctx.has_field(stmt.giving, materialised):
        giving_ref, giving_rr = ctx.resolve_field_ref(stmt.giving, materialised)
        str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            giving_rr, giving_ref.fl, str_reg, giving_ref.offset_reg
        )

    logger.info(
        "CALL %s with %d params (CallWithMemory)", stmt.program, len(stmt.using)
    )


def lower_alter(
    ctx: EmitContext,
    stmt: AlterStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ALTER para-1 TO PROCEED TO para-2."""
    for pt in stmt.proceed_tos:
        target_reg = ctx.const_to_reg(f"para_{pt.target}")
        ctx.emit_inst(
            StoreVar(
                name=VarName(f"__alter_{pt.source}"),
                value_reg=target_reg,
            )
        )
        logger.info("ALTER %s TO PROCEED TO %s", pt.source, pt.target)


def lower_entry(
    ctx: EmitContext,
    stmt: EntryStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ENTRY 'name' — alternate entry point for a subprogram."""
    if stmt.entry_name:
        ctx.emit_inst(Label_(label=CodeLabel(f"entry_{stmt.entry_name}")))
        logger.info("ENTRY %s", stmt.entry_name)


def lower_cancel(
    ctx: EmitContext,
    stmt: CancelStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CANCEL program — no-op for static analysis."""
    for prog in stmt.programs:
        logger.info("CANCEL %s (no-op for static analysis)", prog)
