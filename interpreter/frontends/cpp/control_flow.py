"""C++-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)
from interpreter.frontends.cpp.node_types import CppNodeType


def lower_cpp_if(ctx: TreeSitterEmitContext, node) -> None:
    """Override if lowering to handle C++ condition_clause wrapper.

    C++17 allows ``if (init; cond) { }`` where the init variable is
    scoped to the entire if/else chain.  The init_statement lives inside
    the condition_clause node.
    """
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    # Handle C++17 if-init: condition_clause may contain an init_statement
    init_node = (
        next(
            (c for c in cond_node.children if c.type == CppNodeType.INIT_STATEMENT),
            None,
        )
        if cond_node
        else None
    )
    scope_entered = init_node is not None and ctx.block_scoped
    if scope_entered:
        ctx.enter_block_scope()
    if init_node:
        # Lower the declaration inside init_statement
        for child in init_node.children:
            if child.is_named:
                ctx.lower_stmt(child)

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
            if child.type not in (CppNodeType.ELSE_KEYWORD,) and child.is_named:
                ctx.lower_stmt(child)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)

    if scope_entered:
        ctx.exit_block_scope()


def lower_cpp_while(ctx: TreeSitterEmitContext, node) -> None:
    """Override while lowering to handle C++ condition_clause wrapper."""
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
        and c.type
        not in (
            CppNodeType.TEMPLATE_PARAMETER_LIST,
            CppNodeType.TEMPLATE_PARAMETER_DECLARATION,
        )
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
    right_node = node.child_by_field_name(ctx.constants.assign_right_field)
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    raw_name = "__range_var"
    if declarator_node:
        raw_name = extract_declarator_name(ctx, declarator_node)

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
    ctx.enter_block_scope()
    var_name = ctx.declare_block_var(raw_name)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
    ctx.emit(Opcode.STORE_VAR, operands=[var_name, elem_reg])

    update_label = ctx.fresh_label("range_for_update")
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
    ctx.emit(Opcode.STORE_VAR, operands=["__range_idx", new_idx])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_throw(ctx: TreeSitterEmitContext, node) -> None:
    """Lower C++ throw statement."""
    lower_raise_or_throw(ctx, node, keyword="throw")


def _extract_catch_param(
    ctx: TreeSitterEmitContext, param_decl
) -> tuple[str | None, str | None]:
    """Extract (variable, type) from a C++ catch parameter_declaration.

    Handles both direct identifiers and reference_declarator wrappers
    (e.g., `std::exception& e`).
    """
    # Find identifier — may be a direct child or nested inside reference_declarator
    id_node = next(
        (c for c in param_decl.children if c.type == CppNodeType.IDENTIFIER),
        None,
    )
    if id_node is None:
        ref_decl = next(
            (
                c
                for c in param_decl.children
                if c.type == CppNodeType.REFERENCE_DECLARATOR
            ),
            None,
        )
        if ref_decl:
            id_node = next(
                (c for c in ref_decl.children if c.type == CppNodeType.IDENTIFIER),
                None,
            )
    exc_var = ctx.node_text(id_node) if id_node else None
    type_nodes = [
        c
        for c in param_decl.children
        if c.is_named and c != id_node and c.type != CppNodeType.REFERENCE_DECLARATOR
    ]
    exc_type = ctx.node_text(type_nodes[0]) if type_nodes else None
    return exc_var, exc_type


def lower_try(ctx: TreeSitterEmitContext, node) -> None:
    """Lower C++ try/catch."""
    body_node = node.child_by_field_name("body")
    catch_clauses = []
    for child in node.children:
        if child.type == CppNodeType.CATCH_CLAUSE:
            exc_var = None
            exc_type = None
            # C++ catch uses parameter_list > parameter_declaration
            param_list = next(
                (c for c in child.children if c.type == CppNodeType.PARAMETER_LIST),
                None,
            )
            if param_list:
                param_decl = next(
                    (
                        c
                        for c in param_list.children
                        if c.type == CppNodeType.PARAMETER_DECLARATION
                    ),
                    None,
                )
                if param_decl:
                    exc_var, exc_type = _extract_catch_param(ctx, param_decl)
            catch_body = child.child_by_field_name("body")
            catch_clauses.append(
                {"body": catch_body, "variable": exc_var, "type": exc_type}
            )
    lower_try_catch(ctx, node, body_node, catch_clauses)
