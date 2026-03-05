"""C++-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)


def lower_cpp_if(ctx: TreeSitterEmitContext, node) -> None:
    """Override if lowering to handle C++ condition_clause wrapper."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("consequence")
    alt_node = node.child_by_field_name("alternative")

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

    if alt_node:
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
            node=node,
        )
    else:
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{end_label}",
            node=node,
        )

    ctx.emit(Opcode.LABEL, label=true_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        for child in alt_node.children:
            if child.type not in ("else",) and child.is_named:
                ctx.lower_stmt(child)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_cpp_while(ctx: TreeSitterEmitContext, node) -> None:
    """Override while lowering to handle C++ condition_clause wrapper."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("body")

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


def lower_namespace_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower namespace_definition as a block — descend into body."""
    body_node = node.child_by_field_name("body")
    if body_node:
        ctx.lower_block(body_node)


def lower_template_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower template_declaration — try to lower the inner declaration."""
    inner_decls = [
        c
        for c in node.children
        if c.is_named
        and c.type not in ("template_parameter_list", "template_parameter_declaration")
    ]
    if inner_decls:
        ctx.lower_stmt(inner_decls[-1])
    else:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"template:{ctx.node_text(node)[:60]}"],
            node=node,
        )


def lower_range_for(ctx: TreeSitterEmitContext, node) -> None:
    """Lower for (auto x : container) { body }."""
    from interpreter.frontends.c.declarations import extract_declarator_name

    declarator_node = node.child_by_field_name("declarator")
    right_node = node.child_by_field_name("right")
    body_node = node.child_by_field_name("body")

    var_name = "__range_var"
    if declarator_node:
        var_name = extract_declarator_name(ctx, declarator_node)

    iter_reg = ctx.lower_expr(right_node) if right_node else ctx.fresh_reg()

    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("range_for_cond")
    body_label = ctx.fresh_label("range_for_body")
    end_label = ctx.fresh_label("range_for_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
    ctx.emit(Opcode.STORE_VAR, operands=[var_name, elem_reg])

    update_label = ctx.fresh_label("range_for_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit(Opcode.LABEL, label=update_label)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    new_idx = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
    ctx.emit(Opcode.STORE_VAR, operands=["__range_idx", new_idx])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_throw(ctx: TreeSitterEmitContext, node) -> None:
    """Lower C++ throw statement."""
    lower_raise_or_throw(ctx, node, keyword="throw")


def lower_try(ctx: TreeSitterEmitContext, node) -> None:
    """Lower C++ try/catch."""
    body_node = node.child_by_field_name("body")
    catch_clauses = []
    for child in node.children:
        if child.type == "catch_clause":
            param_node = next(
                (c for c in child.children if c.type == "catch_declarator"),
                None,
            )
            exc_var = None
            exc_type = None
            if param_node:
                id_node = next(
                    (c for c in param_node.children if c.type == "identifier"),
                    None,
                )
                exc_var = ctx.node_text(id_node) if id_node else None
                type_nodes = [
                    c for c in param_node.children if c.is_named and c != id_node
                ]
                if type_nodes:
                    exc_type = ctx.node_text(type_nodes[0])
            catch_body = child.child_by_field_name("body")
            catch_clauses.append(
                {"body": catch_body, "variable": exc_var, "type": exc_type}
            )
    lower_try_catch(ctx, node, body_node, catch_clauses)
