"""C#-specific control flow lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)
from interpreter.frontends.csharp.node_types import CSharpNodeType as NT


def lower_if(ctx: TreeSitterEmitContext, node) -> None:
    """C# if with else-if handled as nested if_statement."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    # If consequence field is not present, find the first block child
    if body_node is None:
        body_node = next((c for c in node.children if c.type == NT.BLOCK), None)

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
        if alt_node.type == NT.IF_STATEMENT:
            lower_if(ctx, alt_node)
        else:
            for child in alt_node.children:
                if child.type not in (NT.ELSE,) and child.is_named:
                    ctx.lower_stmt(child)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_foreach(ctx: TreeSitterEmitContext, node) -> None:
    """Lower foreach (Type var in collection) { body }."""
    left_node = node.child_by_field_name(ctx.constants.assign_left_field)
    right_node = node.child_by_field_name(ctx.constants.assign_right_field)
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    iter_reg = ctx.lower_expr(right_node) if right_node else ctx.fresh_reg()
    raw_name = ctx.node_text(left_node) if left_node else "__foreach_var"

    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("foreach_cond")
    body_label = ctx.fresh_label("foreach_body")
    end_label = ctx.fresh_label("foreach_end")

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
    ctx.emit(Opcode.DECL_VAR, operands=[var_name, elem_reg])

    update_label = ctx.fresh_label("foreach_update")
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
    ctx.emit(Opcode.STORE_VAR, operands=["__foreach_idx", new_idx])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_throw(ctx: TreeSitterEmitContext, node) -> None:
    lower_raise_or_throw(ctx, node, keyword="throw")


def lower_throw_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower C# throw expression (``throw new Exception()`` used as an expression).

    Emits THROW and returns a fresh register (unreachable but satisfies
    the expression-return contract).
    """
    children = [c for c in node.children if c.is_named]
    val_reg = ctx.lower_expr(children[0]) if children else ctx.fresh_reg()
    ctx.emit(Opcode.THROW, operands=[val_reg], node=node)
    return ctx.fresh_reg()


def lower_goto(ctx: TreeSitterEmitContext, node) -> None:
    """Lower C# goto statement — emit BRANCH to the target label."""
    id_node = next(
        (c for c in node.children if c.type in (NT.IDENTIFIER, NT.LABEL_NAME)), None
    )
    label_name = ctx.node_text(id_node) if id_node else "unknown"
    ctx.emit(Opcode.BRANCH, label=label_name, node=node)


def lower_labeled_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower C# labeled statement — emit LABEL, then lower the body statement."""
    id_node = next(
        (c for c in node.children if c.type in (NT.IDENTIFIER, NT.LABEL_NAME)), None
    )
    label_name = ctx.node_text(id_node) if id_node else "unknown"
    ctx.emit(Opcode.LABEL, label=label_name, node=node)
    body_children = [
        c
        for c in node.children
        if c.is_named and c.type not in (NT.IDENTIFIER, NT.LABEL_NAME)
    ]
    for child in body_children:
        ctx.lower_stmt(child)


def lower_do_while(ctx: TreeSitterEmitContext, node) -> None:
    body_node = node.child_by_field_name(ctx.constants.while_body_field)
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)

    body_label = ctx.fresh_label("do_body")
    cond_label = ctx.fresh_label("do_cond")
    end_label = ctx.fresh_label("do_end")

    ctx.emit(Opcode.LABEL, label=body_label)
    ctx.push_loop(cond_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit(Opcode.LABEL, label=cond_label)
    if cond_node:
        cond_reg = ctx.lower_expr(cond_node)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
            node=node,
        )
    else:
        ctx.emit(Opcode.BRANCH, label=body_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_switch(ctx: TreeSitterEmitContext, node) -> None:
    """Lower switch as if/else chain."""
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")

    subject_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    end_label = ctx.fresh_label("switch_end")

    ctx.break_target_stack.append(end_label)

    sections = (
        [c for c in body_node.children if c.type == NT.SWITCH_SECTION]
        if body_node
        else []
    )

    for section in sections:
        pattern_node = next(
            (c for c in section.children if c.type == NT.CONSTANT_PATTERN), None
        )
        body_stmts = [
            c for c in section.children if c.is_named and c.type != NT.CONSTANT_PATTERN
        ]

        arm_label = ctx.fresh_label("case_arm")
        next_label = ctx.fresh_label("case_next")

        if pattern_node:
            # Extract the literal from constant_pattern
            inner = next((c for c in pattern_node.children if c.is_named), None)
            if inner:
                case_reg = ctx.lower_expr(inner)
            else:
                case_reg = ctx.lower_expr(pattern_node)
            cmp_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=cmp_reg,
                operands=["==", subject_reg, case_reg],
                node=section,
            )
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cmp_reg],
                label=f"{arm_label},{next_label}",
            )
        else:
            # default case
            ctx.emit(Opcode.BRANCH, label=arm_label)

        ctx.emit(Opcode.LABEL, label=arm_label)
        for stmt in body_stmts:
            ctx.lower_stmt(stmt)
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    ctx.break_target_stack.pop()
    ctx.emit(Opcode.LABEL, label=end_label)


def lower_switch_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower C# 8 switch expression: subject switch { pattern => expr, ... }."""
    # First named child is the subject expression
    named_children = [c for c in node.children if c.is_named]
    subject_node = named_children[0] if named_children else None
    subject_reg = ctx.lower_expr(subject_node) if subject_node else ctx.fresh_reg()

    result_var = f"__switch_expr_{ctx.label_counter}"
    end_label = ctx.fresh_label("switch_expr_end")

    arms = [c for c in node.children if c.type == NT.SWITCH_EXPRESSION_ARM]

    for arm in arms:
        arm_children = [c for c in arm.children if c.is_named]
        if len(arm_children) < 2:
            continue
        pattern_node = arm_children[0]
        value_node = arm_children[-1]

        arm_label = ctx.fresh_label("switch_arm")
        next_label = ctx.fresh_label("switch_arm_next")

        # Discard pattern _ as default
        is_default = pattern_node.type == NT.DISCARD or (
            pattern_node.type == NT.IDENTIFIER and ctx.node_text(pattern_node) == "_"
        )

        if is_default:
            ctx.emit(Opcode.BRANCH, label=arm_label)
        else:
            pattern_reg = ctx.lower_expr(pattern_node)
            cmp_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=cmp_reg,
                operands=["==", subject_reg, pattern_reg],
                node=arm,
            )
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cmp_reg],
                label=f"{arm_label},{next_label}",
            )

        ctx.emit(Opcode.LABEL, label=arm_label)
        val_reg = ctx.lower_expr(value_node)
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, val_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def lower_try(ctx: TreeSitterEmitContext, node) -> None:
    body_node = node.child_by_field_name("body")
    catch_clauses: list[dict] = []
    finally_node = None
    for child in node.children:
        if child.type == NT.CATCH_CLAUSE:
            decl_node = next(
                (c for c in child.children if c.type == NT.CATCH_DECLARATION),
                None,
            )
            exc_var = None
            exc_type = None
            if decl_node:
                type_node = next(
                    (
                        c
                        for c in decl_node.children
                        if c.type == NT.IDENTIFIER
                        or c.type == NT.QUALIFIED_NAME
                        or c.type == NT.GENERIC_NAME
                    ),
                    None,
                )
                name_node = next(
                    (
                        c
                        for c in decl_node.children
                        if c.type == NT.IDENTIFIER and c != type_node
                    ),
                    None,
                )
                if type_node:
                    exc_type = ctx.node_text(type_node)
                if name_node:
                    exc_var = ctx.node_text(name_node)
            catch_body = child.child_by_field_name("body") or next(
                (c for c in child.children if c.type == NT.BLOCK),
                None,
            )
            catch_clauses.append(
                {"body": catch_body, "variable": exc_var, "type": exc_type}
            )
        elif child.type == NT.FINALLY_CLAUSE:
            finally_node = next(
                (c for c in child.children if c.type == NT.BLOCK),
                None,
            )
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node)


def lower_global_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Unwrap global_statement and lower the inner statement."""
    for child in node.children:
        if child.is_named:
            ctx.lower_stmt(child)


def lower_lock_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower lock(expr) { body }: lower the lock expression, then the body."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        ctx.lower_expr(named_children[0])
    body_node = next((c for c in named_children if c.type == NT.BLOCK), None)
    if body_node:
        ctx.lower_block(body_node)


def lower_using_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower using(resource) { body }: lower resource, then body.

    The resource variable is scoped to the using block.
    """
    named_children = [c for c in node.children if c.is_named]
    has_decl = any(c.type == NT.VARIABLE_DECLARATION for c in named_children)
    scope_entered = has_decl and ctx.block_scoped
    if scope_entered:
        ctx.enter_block_scope()

    for child in named_children:
        if child.type == NT.VARIABLE_DECLARATION:
            from interpreter.frontends.csharp.declarations import (
                lower_variable_declaration,
            )

            lower_variable_declaration(ctx, child)
        elif child.type == NT.BLOCK:
            ctx.lower_block(child)
        elif child.type not in (NT.BLOCK,):
            ctx.lower_expr(child)

    if scope_entered:
        ctx.exit_block_scope()


def lower_checked_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower checked { body }: just lower the body block."""
    body_node = next((c for c in node.children if c.type == NT.BLOCK), None)
    if body_node:
        ctx.lower_block(body_node)


def lower_fixed_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower fixed(decl) { body }: just lower the body block."""
    body_node = next((c for c in node.children if c.type == NT.BLOCK), None)
    if body_node:
        ctx.lower_block(body_node)


def lower_yield_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower yield return expr or yield break."""
    children = [c for c in node.children if c.is_named]
    # Check if this is yield break (no expression child)
    node_text = ctx.node_text(node)
    if "break" in node_text and not children:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["yield_break"],
            node=node,
        )
    else:
        if children:
            val_reg = ctx.lower_expr(children[0])
        else:
            val_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["yield", val_reg],
            node=node,
        )
