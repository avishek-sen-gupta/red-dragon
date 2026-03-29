"""PHP-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.operator_kind import resolve_binop
from interpreter.var_name import VarName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    LoadIndex,
    Return_,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)
from interpreter.frontends.php.node_types import PHPNodeType

logger = logging.getLogger(__name__)


def lower_php_compound(ctx: TreeSitterEmitContext, node) -> None:
    """Lower compound_statement (block with braces)."""
    for child in node.children:
        if (
            child.type not in (PHPNodeType.OPEN_BRACE, PHPNodeType.CLOSE_BRACE)
            and child.is_named
        ):
            ctx.lower_stmt(child)


def lower_php_return(ctx: TreeSitterEmitContext, node) -> None:
    """Lower return statement with PHP-specific filtering."""
    children = [c for c in node.children if c.type != PHPNodeType.RETURN and c.is_named]
    if children:
        val_reg = ctx.lower_expr(children[0])
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Const(result_reg=val_reg, value=ctx.constants.default_return_value)
        )
    ctx.emit_inst(Return_(value_reg=val_reg), node=node)


def lower_php_echo(ctx: TreeSitterEmitContext, node) -> None:
    """Lower echo statement as CALL_FUNCTION('echo', args)."""
    children = [c for c in node.children if c.type != PHPNodeType.ECHO and c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in children]
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=FuncName("echo"), args=tuple(arg_regs)),
        node=node,
    )


def lower_php_if(ctx: TreeSitterEmitContext, node) -> None:
    """Lower PHP if statement with else_clause / else_if_clause support."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name("body")

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    end_label = ctx.fresh_label("if_end")

    # Collect else_clause children
    else_clauses = [
        c
        for c in node.children
        if c.type in (PHPNodeType.ELSE_CLAUSE, PHPNodeType.ELSE_IF_CLAUSE)
    ]

    if else_clauses:
        false_label = ctx.fresh_label("if_false")
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)),
            node=node,
        )
    else:
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(true_label, end_label)),
            node=node,
        )

    ctx.emit_inst(Label_(label=true_label))
    if body_node:
        lower_php_compound(ctx, body_node)
    ctx.emit_inst(Branch(label=end_label))

    if else_clauses:
        ctx.emit_inst(Label_(label=false_label))
        for clause in else_clauses:
            _lower_php_else_clause(ctx, clause, end_label)
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def _lower_php_else_clause(ctx: TreeSitterEmitContext, node, end_label: str) -> None:
    """Lower else_if_clause or else_clause."""
    if node.type == PHPNodeType.ELSE_IF_CLAUSE:
        cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
        body_node = node.child_by_field_name("body")
        cond_reg = ctx.lower_expr(cond_node)
        true_label = ctx.fresh_label("elseif_true")
        false_label = ctx.fresh_label("elseif_false")

        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)),
            node=node,
        )

        ctx.emit_inst(Label_(label=true_label))
        if body_node:
            lower_php_compound(ctx, body_node)
        ctx.emit_inst(Branch(label=end_label))

        ctx.emit_inst(Label_(label=false_label))
    elif node.type == PHPNodeType.ELSE_CLAUSE:
        for child in node.children:
            if (
                child.type
                not in (
                    PHPNodeType.ELSE,
                    PHPNodeType.OPEN_BRACE,
                    PHPNodeType.CLOSE_BRACE,
                )
                and child.is_named
            ):
                if child.type == PHPNodeType.COMPOUND_STATEMENT:
                    lower_php_compound(ctx, child)
                else:
                    ctx.lower_stmt(child)


def lower_php_foreach(ctx: TreeSitterEmitContext, node) -> None:
    """Lower foreach ($arr as $v) or foreach ($arr as $k => $v) as index-based loop."""
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    # Extract iterable, value var, and optional key var from children
    named_children = [c for c in node.children if c.is_named]
    iterable_node = named_children[0] if named_children else None
    binding_node = named_children[1] if len(named_children) > 1 else None

    iter_reg = ctx.lower_expr(iterable_node) if iterable_node else ctx.fresh_reg()

    key_var = None
    value_var = None
    if binding_node and binding_node.type == PHPNodeType.PAIR:
        # $k => $v
        pair_named = [c for c in binding_node.children if c.is_named]
        key_var = ctx.node_text(pair_named[0]) if pair_named else None
        value_var = ctx.node_text(pair_named[1]) if len(pair_named) > 1 else None
    elif binding_node:
        value_var = ctx.node_text(binding_node)

    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=idx_reg, value="0"))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=len_reg, func_name=FuncName("len"), args=(iter_reg,))
    )

    loop_label = ctx.fresh_label("foreach_cond")
    body_label = ctx.fresh_label("foreach_body")
    end_label = ctx.fresh_label("foreach_end")

    ctx.emit_inst(Label_(label=loop_label))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("<"),
            left=idx_reg,
            right=len_reg,
        )
    )
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)))

    ctx.emit_inst(Label_(label=body_label))
    # Store key variable (index) if present
    if key_var:
        ctx.emit_inst(DeclVar(name=VarName(key_var), value_reg=idx_reg))
    # Store value variable (element at index)
    if value_var:
        elem_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadIndex(result_reg=elem_reg, arr_reg=iter_reg, index_reg=idx_reg)
        )
        ctx.emit_inst(DeclVar(name=VarName(value_var), value_reg=elem_reg))

    update_label = ctx.fresh_label("foreach_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit_inst(Label_(label=update_label))
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    new_idx = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=new_idx, operator=resolve_binop("+"), left=idx_reg, right=one_reg
        )
    )
    ctx.emit_inst(StoreVar(name=VarName("__foreach_idx"), value_reg=new_idx))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_php_throw(ctx: TreeSitterEmitContext, node) -> None:
    """Lower throw statement."""
    lower_raise_or_throw(ctx, node, keyword="throw")


def lower_php_try(ctx: TreeSitterEmitContext, node) -> None:
    """Lower try/catch/finally."""
    body_node = node.child_by_field_name("body")
    catch_clauses: list[dict] = []
    finally_node = None
    for child in node.children:
        if child.type == PHPNodeType.CATCH_CLAUSE:
            # PHP catch_clause: type(s) and variable_name
            type_node = next(
                (
                    c
                    for c in child.children
                    if c.type
                    in (
                        PHPNodeType.NAMED_TYPE,
                        PHPNodeType.NAME,
                        PHPNodeType.QUALIFIED_NAME,
                    )
                ),
                None,
            )
            var_node = next(
                (c for c in child.children if c.type == PHPNodeType.VARIABLE_NAME),
                None,
            )
            exc_type = ctx.node_text(type_node) if type_node else None
            exc_var = ctx.node_text(var_node) if var_node else None
            catch_body = child.child_by_field_name("body") or next(
                (c for c in child.children if c.type == PHPNodeType.COMPOUND_STATEMENT),
                None,
            )
            catch_clauses.append(
                {"body": catch_body, "variable": exc_var, "type": exc_type}
            )
        elif child.type == PHPNodeType.FINALLY_CLAUSE:
            finally_node = next(
                (c for c in child.children if c.type == PHPNodeType.COMPOUND_STATEMENT),
                None,
            )
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node)


def lower_php_switch(ctx: TreeSitterEmitContext, node) -> None:
    """Lower switch(expr) { case ... } as an if/else chain."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("body")

    subject_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    end_label = ctx.fresh_label("switch_end")

    ctx.break_target_stack.append(end_label)

    cases = (
        [
            c
            for c in body_node.children
            if c.type in (PHPNodeType.CASE_STATEMENT, PHPNodeType.DEFAULT_STATEMENT)
        ]
        if body_node
        else []
    )

    for case in cases:
        is_default = case.type == PHPNodeType.DEFAULT_STATEMENT
        value_node = case.child_by_field_name("value")
        body_stmts = [c for c in case.children if c.is_named and c != value_node]

        arm_label = ctx.fresh_label("case_arm")
        next_label = ctx.fresh_label("case_next")

        if not is_default and value_node:
            case_reg = ctx.lower_expr(value_node)
            cmp_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=cmp_reg,
                    operator=resolve_binop("=="),
                    left=subject_reg,
                    right=case_reg,
                ),
                node=case,
            )
            ctx.emit_inst(
                BranchIf(cond_reg=cmp_reg, branch_targets=(arm_label, next_label))
            )
        else:
            ctx.emit_inst(Branch(label=arm_label))

        ctx.emit_inst(Label_(label=arm_label))
        for stmt in body_stmts:
            ctx.lower_stmt(stmt)
        ctx.emit_inst(Branch(label=end_label))
        ctx.emit_inst(Label_(label=next_label))

    ctx.break_target_stack.pop()
    ctx.emit_inst(Label_(label=end_label))


def lower_php_do(ctx: TreeSitterEmitContext, node) -> None:
    """Lower do { body } while (condition);"""
    body_node = node.child_by_field_name(ctx.constants.while_body_field)
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)

    body_label = ctx.fresh_label("do_body")
    cond_label = ctx.fresh_label("do_cond")
    end_label = ctx.fresh_label("do_end")

    ctx.emit_inst(Label_(label=body_label))
    ctx.push_loop(cond_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit_inst(Label_(label=cond_label))
    if cond_node:
        cond_reg = ctx.lower_expr(cond_node)
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)),
            node=node,
        )
    else:
        ctx.emit_inst(Branch(label=body_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_php_namespace(ctx: TreeSitterEmitContext, node) -> None:
    """Lower namespace definition: just lower the body compound_statement."""
    body_node = next(
        (c for c in node.children if c.type == PHPNodeType.COMPOUND_STATEMENT), None
    )
    if body_node:
        lower_php_compound(ctx, body_node)


def lower_php_named_label(ctx: TreeSitterEmitContext, node) -> None:
    """Lower name: as LABEL user_{name}."""
    name_node = node.child_by_field_name("name")
    if not name_node:
        name_node = next((c for c in node.children if c.type == PHPNodeType.NAME), None)
    if name_node:
        label_name = CodeLabel(f"user_{ctx.node_text(name_node)}")
        ctx.emit_inst(Label_(label=label_name), node=node)
    else:
        logger.warning(
            "named_label_statement without name: %s", ctx.node_text(node)[:40]
        )


def lower_php_goto(ctx: TreeSitterEmitContext, node) -> None:
    """Lower goto name; as BRANCH user_{name}."""
    name_node = node.child_by_field_name("label")
    if not name_node:
        name_node = next((c for c in node.children if c.type == PHPNodeType.NAME), None)
    if name_node:
        target_label = CodeLabel(f"user_{ctx.node_text(name_node)}")
        ctx.emit_inst(Branch(label=target_label), node=node)
    else:
        logger.warning("goto_statement without label: %s", ctx.node_text(node)[:40])
