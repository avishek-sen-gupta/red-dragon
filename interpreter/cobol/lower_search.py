# pyright: standard
"""SEARCH statement lowering."""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_statements import SearchStatement
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.operator_kind import resolve_binop
from interpreter.var_name import VarName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    Label_,
    LoadVar,
    StoreVar,
)
from interpreter.register import Register

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
    counter_var = ctx.fresh_name("__search_ctr")
    zero_reg = ctx.const_to_reg(0)
    ctx.emit_inst(
        StoreVar(name=VarName(counter_var), value_reg=Register(str(zero_reg)))
    )

    max_reg = ctx.const_to_reg(max_iterations)

    ctx.emit_inst(Label_(label=loop_label))

    ctr_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=ctr_reg, name=VarName(counter_var)))
    bound_cond = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=bound_cond,
            operator=resolve_binop(">="),
            left=ctr_reg,
            right=Register(str(max_reg)),
        )
    )
    body_label = ctx.fresh_label("search_body")
    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(bound_cond)),
            branch_targets=(at_end_label, body_label),
        )
    )

    ctx.emit_inst(Label_(label=body_label))
    for when in stmt.whens:
        if not when.condition:
            continue
        cond_reg = ctx.lower_condition(when.condition, layout, region_reg)
        when_true = ctx.fresh_label("search_when_true")
        when_next = ctx.fresh_label("search_when_next")
        ctx.emit_inst(
            BranchIf(
                cond_reg=Register(str(cond_reg)),
                branch_targets=(when_true, when_next),
            )
        )
        ctx.emit_inst(Label_(label=when_true))
        for child in when.children:
            ctx.lower_statement(child, layout, region_reg)
        ctx.emit_inst(Branch(label=end_label))
        ctx.emit_inst(Label_(label=when_next))

    ctx.emit_inst(Branch(label=increment_label))
    ctx.emit_inst(Label_(label=increment_label))

    if stmt.varying and ctx.has_field(stmt.varying, layout):
        varying_ref = ctx.resolve_field_ref(stmt.varying, layout, region_reg)
        decoded_reg = ctx.emit_decode_field(
            region_reg, varying_ref.fl, varying_ref.offset_reg
        )
        one_reg = ctx.const_to_reg(1)
        inc_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=inc_reg,
                operator=resolve_binop("+"),
                left=Register(str(decoded_reg)),
                right=Register(str(one_reg)),
            )
        )
        str_reg = ctx.emit_to_string(inc_reg)  # type: ignore[arg-type]  # see red-dragon-pn3f
        ctx.emit_encode_and_write(
            region_reg, varying_ref.fl, str_reg, varying_ref.offset_reg
        )

    ctr_reg2 = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=ctr_reg2, name=VarName(counter_var)))
    one_ctr = ctx.const_to_reg(1)
    inc_ctr = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=inc_ctr,
            operator=resolve_binop("+"),
            left=ctr_reg2,
            right=Register(str(one_ctr)),
        )
    )
    ctx.emit_inst(StoreVar(name=VarName(counter_var), value_reg=inc_ctr))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=at_end_label))
    for child in stmt.at_end:
        ctx.lower_statement(child, layout, region_reg)

    ctx.emit_inst(Label_(label=end_label))
