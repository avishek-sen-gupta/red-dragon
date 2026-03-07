"""Lua-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode

logger = logging.getLogger(__name__)


def lower_lua_if(ctx: TreeSitterEmitContext, node) -> None:
    """Lower if_statement with elseif_statement and else_statement children."""
    condition_node = node.child_by_field_name(ctx.constants.if_condition_field)
    consequence_node = node.child_by_field_name(ctx.constants.if_consequence_field)

    cond_reg = ctx.lower_expr(condition_node)
    true_label = ctx.fresh_label("if_true")
    end_label = ctx.fresh_label("if_end")

    elseif_nodes = [c for c in node.children if c.type == "elseif_statement"]
    else_node = next((c for c in node.children if c.type == "else_statement"), None)
    has_alternative = len(elseif_nodes) > 0 or else_node is not None
    false_label = ctx.fresh_label("if_false") if has_alternative else end_label

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{true_label},{false_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=true_label)
    if consequence_node:
        ctx.lower_block(consequence_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if has_alternative:
        ctx.emit(Opcode.LABEL, label=false_label)
        _lower_lua_elseif_chain(ctx, elseif_nodes, else_node, end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def _lower_lua_elseif_chain(
    ctx: TreeSitterEmitContext, elseif_nodes, else_node, end_label: str
) -> None:
    """Lower a chain of elseif_statement nodes followed by optional else."""
    if not elseif_nodes:
        if else_node:
            for child in else_node.children:
                if child.is_named and child.type not in ("else",):
                    ctx.lower_block(child)
        return

    current = elseif_nodes[0]
    remaining = elseif_nodes[1:]

    cond_node = current.child_by_field_name(ctx.constants.if_condition_field)
    body_node = current.child_by_field_name(ctx.constants.if_consequence_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("elseif_true")
    has_more = len(remaining) > 0 or else_node is not None
    false_label = ctx.fresh_label("elseif_false") if has_more else end_label

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{true_label},{false_label}",
        node=current,
    )

    ctx.emit(Opcode.LABEL, label=true_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if has_more:
        ctx.emit(Opcode.LABEL, label=false_label)
        _lower_lua_elseif_chain(ctx, remaining, else_node, end_label)


def lower_lua_while(ctx: TreeSitterEmitContext, node) -> None:
    """Lower while_statement."""
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)
    body_node = node.child_by_field_name(ctx.constants.while_body_field)

    loop_label = ctx.fresh_label("while_cond")
    body_label = ctx.fresh_label("while_body")
    end_label = ctx.fresh_label("while_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.lower_expr(cond_node)
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(loop_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_lua_for(ctx: TreeSitterEmitContext, node) -> None:
    """Lower for_statement -- dispatches on for_numeric_clause vs for_generic_clause."""
    numeric_clause = next(
        (c for c in node.children if c.type == "for_numeric_clause"), None
    )
    generic_clause = next(
        (c for c in node.children if c.type == "for_generic_clause"), None
    )
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    if numeric_clause:
        _lower_lua_for_numeric(ctx, numeric_clause, body_node, node)
    elif generic_clause:
        _lower_lua_for_generic(ctx, generic_clause, body_node, node)
    else:
        logger.warning(
            "Lua for_statement: no numeric or generic clause found in %s",
            ctx.node_text(node)[:60],
        )


def _lower_lua_for_numeric(
    ctx: TreeSitterEmitContext, clause, body_node, for_node
) -> None:
    """Lower for i = start, end [, step] do ... end."""
    name_node = clause.child_by_field_name("name")
    start_node = clause.child_by_field_name("start")
    end_node = clause.child_by_field_name("end")
    step_node = clause.child_by_field_name("step")

    var_name = ctx.node_text(name_node) if name_node else "__for_var"
    start_reg = ctx.lower_expr(start_node) if start_node else ctx.fresh_reg()
    end_reg = ctx.lower_expr(end_node) if end_node else ctx.fresh_reg()

    ctx.emit(Opcode.STORE_VAR, operands=[var_name, start_reg])

    step_reg = ctx.fresh_reg()
    if step_node:
        step_reg = ctx.lower_expr(step_node)
    else:
        ctx.emit(Opcode.CONST, result_reg=step_reg, operands=["1"])

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    current_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=current_reg, operands=[var_name])
    cond_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=cond_reg,
        operands=["<=", current_reg, end_reg],
    )
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
        node=for_node,
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    update_label = ctx.fresh_label("for_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit(Opcode.LABEL, label=update_label)
    next_reg = ctx.fresh_reg()
    cur_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=cur_reg, operands=[var_name])
    ctx.emit(
        Opcode.BINOP,
        result_reg=next_reg,
        operands=["+", cur_reg, step_reg],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[var_name, next_reg])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def _lower_lua_for_generic(
    ctx: TreeSitterEmitContext, clause, body_node, for_node
) -> None:
    """Lower for k, v in ipairs/pairs(t) do ... end as index-based iteration."""
    # Extract variable names from variable_list
    var_list = next((c for c in clause.children if c.type == "variable_list"), None)
    expr_list = next((c for c in clause.children if c.type == "expression_list"), None)

    var_names = (
        [ctx.node_text(c) for c in var_list.children if c.is_named] if var_list else []
    )

    # Lower the iterable expression (e.g., pairs(t) or ipairs(t))
    iter_reg = ctx.lower_expr(expr_list) if expr_list else ctx.fresh_reg()

    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("generic_for_cond")
    body_label = ctx.fresh_label("generic_for_body")
    end_label = ctx.fresh_label("generic_for_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    # First var = index, second var = element
    if len(var_names) >= 1:
        ctx.emit(Opcode.STORE_VAR, operands=[var_names[0], idx_reg])
    if len(var_names) >= 2:
        elem_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[iter_reg, idx_reg],
        )
        ctx.emit(Opcode.STORE_VAR, operands=[var_names[1], elem_reg])

    update_label = ctx.fresh_label("generic_for_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit(Opcode.LABEL, label=update_label)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    new_idx = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
    ctx.emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_lua_repeat(ctx: TreeSitterEmitContext, node) -> None:
    """Lower repeat ... until cond (execute body first, then check)."""
    body_node = node.child_by_field_name(ctx.constants.while_body_field)
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)

    body_label = ctx.fresh_label("repeat_body")
    end_label = ctx.fresh_label("repeat_end")

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(body_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    cond_reg = ctx.lower_expr(cond_node)
    # repeat-until: loop continues while condition is FALSE
    negated_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=negated_reg,
        operands=["not", cond_reg],
        node=node,
    )
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[negated_reg],
        label=f"{body_label},{end_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_lua_do(ctx: TreeSitterEmitContext, node) -> None:
    """Lower do ... end as a plain block."""
    body_node = node.child_by_field_name("body")
    if body_node:
        ctx.lower_block(body_node)
    else:
        for child in node.children:
            if child.is_named and child.type not in ("do", "end"):
                ctx.lower_stmt(child)


def lower_lua_goto(ctx: TreeSitterEmitContext, node) -> None:
    """Lower goto_statement -- BRANCH to the named label."""
    named_children = [c for c in node.children if c.is_named]
    label_name = ctx.node_text(named_children[0]) if named_children else "unknown"
    logger.debug("Lowering goto -> %s at %s", label_name, ctx.source_loc(node))
    ctx.emit(
        Opcode.BRANCH,
        label=label_name,
        node=node,
    )


def lower_lua_label(ctx: TreeSitterEmitContext, node) -> None:
    """Lower label_statement (::name::) -- emit LABEL with the name."""
    named_children = [c for c in node.children if c.is_named]
    label_name = ctx.node_text(named_children[0]) if named_children else "unknown"
    logger.debug("Lowering label :: %s :: at %s", label_name, ctx.source_loc(node))
    ctx.emit(Opcode.LABEL, label=label_name)
