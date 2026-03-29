"""CALL, ALTER, ENTRY, CANCEL statement lowering."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_statements import (
    AlterStatement,
    CallStatement,
    CancelStatement,
    EntryStatement,
)
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
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
    layout: DataLayout,
    region_reg: str,
) -> None:
    """CALL 'program' USING params — symbolic subprogram invocation."""
    arg_regs: list[str] = []
    for param in stmt.using:
        if ctx.has_field(param.name, layout):
            ref = ctx.resolve_field_ref(param.name, layout, region_reg)
            arg_regs.append(ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg))
        else:
            arg_regs.append(ctx.const_to_reg(param.name))

    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName(stmt.program),
            args=tuple(Register(str(a)) for a in arg_regs),
        )
    )

    if stmt.giving and ctx.has_field(stmt.giving, layout):
        giving_ref = ctx.resolve_field_ref(stmt.giving, layout, region_reg)
        str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            region_reg, giving_ref.fl, str_reg, giving_ref.offset_reg
        )

    logger.info("CALL %s with %d params (symbolic)", stmt.program, len(stmt.using))


def lower_alter(
    ctx: EmitContext,
    stmt: AlterStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """ALTER para-1 TO PROCEED TO para-2."""
    for pt in stmt.proceed_tos:
        target_reg = ctx.const_to_reg(f"para_{pt.target}")
        ctx.emit_inst(
            StoreVar(
                name=VarName(f"__alter_{pt.source}"),
                value_reg=Register(str(target_reg)),
            )
        )
        logger.info("ALTER %s TO PROCEED TO %s", pt.source, pt.target)


def lower_entry(
    ctx: EmitContext,
    stmt: EntryStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """ENTRY 'name' — alternate entry point for a subprogram."""
    if stmt.entry_name:
        ctx.emit_inst(Label_(label=CodeLabel(f"entry_{stmt.entry_name}")))
        logger.info("ENTRY %s", stmt.entry_name)


def lower_cancel(
    ctx: EmitContext,
    stmt: CancelStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """CANCEL program — no-op for static analysis."""
    for prog in stmt.programs:
        logger.info("CANCEL %s (no-op for static analysis)", prog)
