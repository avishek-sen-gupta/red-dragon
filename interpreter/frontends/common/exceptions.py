"""Common exception lowerers — pure functions taking (ctx, node).

Extracted from BaseFrontend: try_catch, raise_or_throw.
"""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode, CodeLabel, NO_LABEL
from interpreter import constants
from interpreter.constants import DEFAULT_EXCEPTION_TYPE


def lower_try_catch(
    ctx: TreeSitterEmitContext,
    node,
    body_node,
    catch_clauses: list[dict],
    finally_node=None,
    else_node=None,
) -> None:
    """Lower try/catch/finally into labeled blocks connected by BRANCH.

    Each catch dict: {"body": node, "variable": str|None, "type": str|None}
    """
    try_body_label = ctx.fresh_label("try_body")
    catch_labels = [ctx.fresh_label(f"catch_{i}") for i in range(len(catch_clauses))]
    finally_label = ctx.fresh_label("try_finally") if finally_node else NO_LABEL
    else_label = ctx.fresh_label("try_else") if else_node else NO_LABEL
    end_label = ctx.fresh_label("try_end")

    exit_target = finally_label if finally_label.is_present() else end_label

    # ── push exception handler ──
    ctx.emit(
        Opcode.TRY_PUSH,
        operands=[
            catch_labels,
            finally_label,
            end_label,
        ],
    )

    # ── try body ──
    ctx.emit(Opcode.LABEL, label=try_body_label)
    if body_node:
        ctx.lower_block(body_node)
    # ── pop exception handler (normal exit) ──
    ctx.emit(Opcode.TRY_POP)
    # After try body: jump to else (if present), then finally/end
    if else_label.is_present():
        ctx.emit(Opcode.BRANCH, label=else_label)
    else:
        ctx.emit(Opcode.BRANCH, label=exit_target)

    # ── catch clauses ──
    for i, clause in enumerate(catch_clauses):
        ctx.emit(Opcode.LABEL, label=catch_labels[i])
        ctx.enter_block_scope()
        exc_type = clause.get("type", DEFAULT_EXCEPTION_TYPE) or DEFAULT_EXCEPTION_TYPE
        exc_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=exc_reg,
            operands=[f"{constants.CAUGHT_EXCEPTION_PREFIX}:{exc_type}"],
            node=node,
        )
        exc_var = clause.get("variable")
        if exc_var:
            resolved_var = ctx.declare_block_var(exc_var)
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[resolved_var, exc_reg],
                node=node,
            )
        catch_body = clause.get("body")
        if catch_body:
            ctx.lower_block(catch_body)
        ctx.exit_block_scope()
        ctx.emit(Opcode.BRANCH, label=exit_target)

    # ── else clause (Python/Ruby) ──
    if else_node:
        ctx.emit(Opcode.LABEL, label=else_label)
        ctx.lower_block(else_node)
        ctx.emit(Opcode.BRANCH, label=finally_label if finally_label.is_present() else end_label)

    # ── finally clause ──
    if finally_node:
        ctx.emit(Opcode.LABEL, label=finally_label)
        ctx.lower_block(finally_node)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_raise_or_throw(
    ctx: TreeSitterEmitContext, node, keyword: str = "raise"
) -> None:
    children = [c for c in node.children if c.type != keyword]
    if children:
        val_reg = ctx.lower_expr(children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.default_return_value],
        )
    ctx.emit(
        Opcode.THROW,
        operands=[val_reg],
        node=node,
    )
