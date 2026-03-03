"""SEARCH statement lowering."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_statements import SearchStatement
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.ir import Opcode

logger = logging.getLogger(__name__)


def lower_search(
    ctx: EmitContext,
    stmt: SearchStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """SEARCH table VARYING index WHEN cond ... AT END ..."""
    loop_label = ctx.fresh_label("search_loop")
    end_label = ctx.fresh_label("search_end")
    at_end_label = ctx.fresh_label("search_at_end")
    increment_label = ctx.fresh_label("search_incr")

    max_iterations = 256
    counter_var = ctx.fresh_label("__search_ctr")
    zero_reg = ctx.const_to_reg(0)
    ctx.emit(Opcode.STORE_VAR, operands=[counter_var, zero_reg])

    max_reg = ctx.const_to_reg(max_iterations)

    ctx.emit(Opcode.LABEL, label=loop_label)

    ctr_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=ctr_reg, operands=[counter_var])
    bound_cond = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=bound_cond,
        operands=[">=", ctr_reg, max_reg],
    )
    body_label = ctx.fresh_label("search_body")
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[bound_cond],
        label=f"{at_end_label},{body_label}",
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    for when in stmt.whens:
        if not when.condition:
            continue
        cond_reg = ctx.lower_condition(when.condition, layout, region_reg)
        when_true = ctx.fresh_label("search_when_true")
        when_next = ctx.fresh_label("search_when_next")
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{when_true},{when_next}",
        )
        ctx.emit(Opcode.LABEL, label=when_true)
        for child in when.children:
            ctx.lower_statement(child, layout, region_reg)
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=when_next)

    ctx.emit(Opcode.BRANCH, label=increment_label)
    ctx.emit(Opcode.LABEL, label=increment_label)

    if stmt.varying and ctx.has_field(stmt.varying, layout):
        varying_ref = ctx.resolve_field_ref(stmt.varying, layout, region_reg)
        decoded_reg = ctx.emit_decode_field(
            region_reg, varying_ref.fl, varying_ref.offset_reg
        )
        one_reg = ctx.const_to_reg(1)
        inc_reg = ctx.fresh_reg()
        ctx.emit(Opcode.BINOP, result_reg=inc_reg, operands=["+", decoded_reg, one_reg])
        str_reg = ctx.emit_to_string(inc_reg)
        ctx.emit_encode_and_write(
            region_reg, varying_ref.fl, str_reg, varying_ref.offset_reg
        )

    ctr_reg2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=ctr_reg2, operands=[counter_var])
    one_ctr = ctx.const_to_reg(1)
    inc_ctr = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=inc_ctr, operands=["+", ctr_reg2, one_ctr])
    ctx.emit(Opcode.STORE_VAR, operands=[counter_var, inc_ctr])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=at_end_label)
    for child in stmt.at_end:
        ctx.lower_statement(child, layout, region_reg)

    ctx.emit(Opcode.LABEL, label=end_label)
