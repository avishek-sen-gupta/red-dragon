"""Lua-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode, CodeLabel
from interpreter.frontends.lua.node_types import LuaNodeType
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    Binop,
    Unop,
    CallFunction,
    LoadIndex,
    Label_,
    Branch,
    BranchIf,
)

logger = logging.getLogger(__name__)


def lower_lua_if(ctx: TreeSitterEmitContext, node) -> None:
    """Lower if_statement with elseif_statement and else_statement children."""
    condition_node = node.child_by_field_name(ctx.constants.if_condition_field)
    consequence_node = node.child_by_field_name(ctx.constants.if_consequence_field)

    cond_reg = ctx.lower_expr(condition_node)
    true_label = ctx.fresh_label("if_true")
    end_label = ctx.fresh_label("if_end")

    elseif_nodes = [c for c in node.children if c.type == LuaNodeType.ELSEIF_STATEMENT]
    else_node = next(
        (c for c in node.children if c.type == LuaNodeType.ELSE_STATEMENT), None
    )
    has_alternative = len(elseif_nodes) > 0 or else_node is not None
    false_label = ctx.fresh_label("if_false") if has_alternative else end_label

    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)), node=node
    )

    ctx.emit_inst(Label_(label=true_label))
    if consequence_node:
        ctx.lower_block(consequence_node)
    ctx.emit_inst(Branch(label=end_label))

    if has_alternative:
        ctx.emit_inst(Label_(label=false_label))
        _lower_lua_elseif_chain(ctx, elseif_nodes, else_node, end_label)

    ctx.emit_inst(Label_(label=end_label))


def _lower_lua_elseif_chain(
    ctx: TreeSitterEmitContext, elseif_nodes, else_node, end_label: str
) -> None:
    """Lower a chain of elseif_statement nodes followed by optional else."""
    if not elseif_nodes:
        if else_node:
            for child in else_node.children:
                if child.is_named and child.type not in (LuaNodeType.ELSE,):
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

    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)),
        node=current,
    )

    ctx.emit_inst(Label_(label=true_label))
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit_inst(Branch(label=end_label))

    if has_more:
        ctx.emit_inst(Label_(label=false_label))
        _lower_lua_elseif_chain(ctx, remaining, else_node, end_label)


def lower_lua_while(ctx: TreeSitterEmitContext, node) -> None:
    """Lower while_statement."""
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)
    body_node = node.child_by_field_name(ctx.constants.while_body_field)

    loop_label = ctx.fresh_label("while_cond")
    body_label = ctx.fresh_label("while_body")
    end_label = ctx.fresh_label("while_end")

    ctx.emit_inst(Label_(label=loop_label))
    cond_reg = ctx.lower_expr(cond_node)
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)), node=node
    )

    ctx.emit_inst(Label_(label=body_label))
    ctx.push_loop(loop_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_lua_for(ctx: TreeSitterEmitContext, node) -> None:
    """Lower for_statement -- dispatches on for_numeric_clause vs for_generic_clause."""
    numeric_clause = next(
        (c for c in node.children if c.type == LuaNodeType.FOR_NUMERIC_CLAUSE), None
    )
    generic_clause = next(
        (c for c in node.children if c.type == LuaNodeType.FOR_GENERIC_CLAUSE), None
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

    ctx.emit_inst(DeclVar(name=var_name, value_reg=start_reg))

    step_reg = ctx.fresh_reg()
    if step_node:
        step_reg = ctx.lower_expr(step_node)
    else:
        ctx.emit_inst(Const(result_reg=step_reg, value="1"))

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

    ctx.emit_inst(Label_(label=loop_label))
    current_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=current_reg, name=var_name))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(result_reg=cond_reg, operator="<=", left=current_reg, right=end_reg)
    )
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)),
        node=for_node,
    )

    ctx.emit_inst(Label_(label=body_label))
    update_label = ctx.fresh_label("for_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit_inst(Label_(label=update_label))
    next_reg = ctx.fresh_reg()
    cur_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=cur_reg, name=var_name))
    ctx.emit_inst(
        Binop(result_reg=next_reg, operator="+", left=cur_reg, right=step_reg)
    )
    ctx.emit_inst(StoreVar(name=var_name, value_reg=next_reg))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


_ITERATOR_WRAPPERS = frozenset({"ipairs", "pairs"})


def _strip_iterator_wrapper(ctx: TreeSitterEmitContext, expr_list_node):
    """If the expression list is a single ipairs(t)/pairs(t) call, return t.

    Otherwise return the original expression list node unchanged.
    """
    named = [c for c in expr_list_node.children if c.is_named]
    if len(named) != 1 or named[0].type != LuaNodeType.FUNCTION_CALL:
        return expr_list_node
    call_node = named[0]
    name_node = call_node.child_by_field_name("name")
    if name_node is None or ctx.node_text(name_node) not in _ITERATOR_WRAPPERS:
        return expr_list_node
    args_node = call_node.child_by_field_name(ctx.constants.call_arguments_field)
    if args_node is None:
        return expr_list_node
    inner_args = [c for c in args_node.children if c.is_named]
    if len(inner_args) != 1:
        return expr_list_node
    return inner_args[0]


def _lower_lua_for_generic(
    ctx: TreeSitterEmitContext, clause, body_node, for_node
) -> None:
    """Lower for k, v in ipairs/pairs(t) do ... end as index-based iteration."""
    # Extract variable names from variable_list
    var_list = next(
        (c for c in clause.children if c.type == LuaNodeType.VARIABLE_LIST), None
    )
    expr_list = next(
        (c for c in clause.children if c.type == LuaNodeType.EXPRESSION_LIST), None
    )

    var_names = (
        [ctx.node_text(c) for c in var_list.children if c.is_named] if var_list else []
    )

    # Strip ipairs()/pairs() wrappers — these are semantically no-ops for
    # index-based iteration.  Lower the inner argument directly instead.
    iterable_node = _strip_iterator_wrapper(ctx, expr_list) if expr_list else None
    iter_reg = ctx.lower_expr(iterable_node) if iterable_node else ctx.fresh_reg()

    init_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_idx, value="0"))
    ctx.emit_inst(DeclVar(name="__for_idx", value_reg=init_idx))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(result_reg=len_reg, func_name="len", args=(iter_reg,)))

    loop_label = ctx.fresh_label("generic_for_cond")
    body_label = ctx.fresh_label("generic_for_body")
    end_label = ctx.fresh_label("generic_for_end")

    ctx.emit_inst(Label_(label=loop_label))
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=idx_reg, name="__for_idx"))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(Binop(result_reg=cond_reg, operator="<", left=idx_reg, right=len_reg))
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)))

    ctx.emit_inst(Label_(label=body_label))
    # First var = index, second var = element
    if len(var_names) >= 1:
        ctx.emit_inst(DeclVar(name=var_names[0], value_reg=idx_reg))
    if len(var_names) >= 2:
        elem_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadIndex(result_reg=elem_reg, arr_reg=iter_reg, index_reg=idx_reg)
        )
        ctx.emit_inst(DeclVar(name=var_names[1], value_reg=elem_reg))

    update_label = ctx.fresh_label("generic_for_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit_inst(Label_(label=update_label))
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    new_idx = ctx.fresh_reg()
    ctx.emit_inst(Binop(result_reg=new_idx, operator="+", left=idx_reg, right=one_reg))
    ctx.emit_inst(StoreVar(name="__for_idx", value_reg=new_idx))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_lua_repeat(ctx: TreeSitterEmitContext, node) -> None:
    """Lower repeat ... until cond (execute body first, then check)."""
    body_node = node.child_by_field_name(ctx.constants.while_body_field)
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)

    body_label = ctx.fresh_label("repeat_body")
    end_label = ctx.fresh_label("repeat_end")

    ctx.emit_inst(Label_(label=body_label))
    ctx.push_loop(body_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    cond_reg = ctx.lower_expr(cond_node)
    # repeat-until: loop continues while condition is FALSE
    negated_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Unop(result_reg=negated_reg, operator="not", operand=cond_reg), node=node
    )
    ctx.emit_inst(
        BranchIf(cond_reg=negated_reg, branch_targets=(body_label, end_label)),
        node=node,
    )

    ctx.emit_inst(Label_(label=end_label))


def lower_lua_do(ctx: TreeSitterEmitContext, node) -> None:
    """Lower do ... end as a plain block."""
    body_node = node.child_by_field_name("body")
    if body_node:
        ctx.lower_block(body_node)
    else:
        for child in node.children:
            if child.is_named and child.type not in (LuaNodeType.DO, LuaNodeType.END):
                ctx.lower_stmt(child)


def lower_lua_goto(ctx: TreeSitterEmitContext, node) -> None:
    """Lower goto_statement -- BRANCH to the named label."""
    named_children = [c for c in node.children if c.is_named]
    label_name = ctx.node_text(named_children[0]) if named_children else "unknown"
    logger.debug("Lowering goto -> %s at %s", label_name, ctx.source_loc(node))
    ctx.emit_inst(Branch(label=CodeLabel(label_name)), node=node)


def lower_lua_label(ctx: TreeSitterEmitContext, node) -> None:
    """Lower label_statement (::name::) -- emit LABEL with the name."""
    named_children = [c for c in node.children if c.is_named]
    label_name = ctx.node_text(named_children[0]) if named_children else "unknown"
    logger.debug("Lowering label :: %s :: at %s", label_name, ctx.source_loc(node))
    ctx.emit_inst(Label_(label=CodeLabel(label_name)))
