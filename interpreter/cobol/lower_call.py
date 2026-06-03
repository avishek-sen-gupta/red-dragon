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
    CallFunction,
    Label_,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.register import Register

logger = logging.getLogger(__name__)


def lower_call(
    ctx: EmitContext,
    stmt: CallStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CALL 'program' USING params — symbolic subprogram invocation."""
    arg_regs: list[Register] = []
    for param in stmt.using:
        if ctx.has_field(param.name, materialised):
            ref, rr = ctx.resolve_field_ref(param.name, materialised)
            arg_regs.append(ctx.emit_decode_field(rr, ref.fl, ref.offset_reg))
        else:
            arg_regs.append(ctx.const_to_reg(param.name))

    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName(stmt.program),
            args=tuple(arg_regs),
        )
    )

    if stmt.giving and ctx.has_field(stmt.giving, materialised):
        giving_ref, giving_rr = ctx.resolve_field_ref(stmt.giving, materialised)
        str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            giving_rr, giving_ref.fl, str_reg, giving_ref.offset_reg
        )

    logger.info("CALL %s with %d params (symbolic)", stmt.program, len(stmt.using))


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
