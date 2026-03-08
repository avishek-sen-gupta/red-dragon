"""Rust-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter.frontends.rust.expressions import lower_if_expr

logger = logging.getLogger(__name__)


def lower_if_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower if as a statement (discard result)."""
    lower_if_expr(ctx, node)


def lower_loop(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `loop { ... }` -- infinite loop."""
    body_node = node.child_by_field_name(ctx.constants.while_body_field)
    loop_label = ctx.fresh_label("loop_top")
    end_label = ctx.fresh_label("loop_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    ctx.push_loop(loop_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.emit(Opcode.BRANCH, label=loop_label)
    ctx.emit(Opcode.LABEL, label=end_label)


def lower_for(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `for pattern in value { body }`."""
    pattern_node = node.child_by_field_name("pattern")
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    raw_name = ctx.node_text(pattern_node) if pattern_node else "__for_var"
    iter_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()

    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.enter_block_scope()
    var_name = ctx.declare_block_var(raw_name)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
    ctx.emit(Opcode.STORE_VAR, operands=[var_name, elem_reg])

    update_label = ctx.fresh_label("for_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.exit_block_scope()

    ctx.emit(Opcode.LABEL, label=update_label)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    new_idx = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
    ctx.emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_return_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower return as statement (discard result)."""
    from interpreter.frontends.rust.expressions import lower_return_expr

    lower_return_expr(ctx, node)


def lower_macro_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower macro_invocation as statement."""
    from interpreter.frontends.rust.expressions import lower_macro_invocation

    lower_macro_invocation(ctx, node)
