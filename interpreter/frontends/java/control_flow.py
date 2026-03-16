"""Java-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)
from interpreter.frontends.java.expressions import (
    extract_call_args_unwrap,
    lower_java_store_target,
)
from interpreter.frontends.java.node_types import JavaNodeType


def lower_if(ctx: TreeSitterEmitContext, node) -> None:
    """Java if with else-if handled as nested if_statement."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

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
    ctx.lower_block(body_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        if alt_node.type == JavaNodeType.IF_STATEMENT:
            lower_if(ctx, alt_node)
        else:
            for child in alt_node.children:
                if child.type not in (JavaNodeType.ELSE,) and child.is_named:
                    ctx.lower_stmt(child)
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_enhanced_for(ctx: TreeSitterEmitContext, node) -> None:
    """Lower for (Type var : iterable) { body }."""
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    iter_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    raw_name = ctx.node_text(name_node) if name_node else "__for_var"

    init_idx = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=init_idx, operands=["0"])
    ctx.emit(Opcode.DECL_VAR, operands=["__for_idx", init_idx])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("for_cond")
    body_label = ctx.fresh_label("for_body")
    end_label = ctx.fresh_label("for_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=idx_reg, operands=["__for_idx"])
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

    update_label = ctx.fresh_label("for_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.exit_block_scope()

    # increment
    ctx.emit(Opcode.LABEL, label=update_label)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    new_idx = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
    ctx.emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
    ctx.emit(Opcode.BRANCH, label=loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_java_switch(ctx: TreeSitterEmitContext, node) -> None:
    """Lower switch(expr) { case ... } as an if/else chain."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("body")

    subject_reg = ctx.lower_expr(cond_node)
    end_label = ctx.fresh_label("switch_end")

    ctx.break_target_stack.append(end_label)

    groups = (
        [
            c
            for c in body_node.children
            if c.type == JavaNodeType.SWITCH_BLOCK_STATEMENT_GROUP
        ]
        if body_node
        else []
    )

    for group in groups:
        label_node = next(
            (c for c in group.children if c.type == JavaNodeType.SWITCH_LABEL), None
        )
        body_stmts = [
            c
            for c in group.children
            if c.is_named and c.type != JavaNodeType.SWITCH_LABEL
        ]

        arm_label = ctx.fresh_label("case_arm")
        next_label = ctx.fresh_label("case_next")

        is_default = label_node is not None and not any(
            c.is_named for c in label_node.children
        )

        if label_node and not is_default:
            case_value = next((c for c in label_node.children if c.is_named), None)
            if case_value:
                case_reg = ctx.lower_expr(case_value)
                cmp_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.BINOP,
                    result_reg=cmp_reg,
                    operands=["==", subject_reg, case_reg],
                    node=group,
                )
                ctx.emit(
                    Opcode.BRANCH_IF,
                    operands=[cmp_reg],
                    label=f"{arm_label},{next_label}",
                )
            else:
                ctx.emit(Opcode.BRANCH, label=arm_label)
        else:
            ctx.emit(Opcode.BRANCH, label=arm_label)

        ctx.emit(Opcode.LABEL, label=arm_label)
        for stmt in body_stmts:
            ctx.lower_stmt(stmt)
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    ctx.break_target_stack.pop()
    ctx.emit(Opcode.LABEL, label=end_label)


def lower_java_switch_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower switch expression as if/else chain, returning last arm value."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("body")

    subject_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    result_var = f"__switch_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("switch_end")

    ctx.switch_result_stack.append(result_var)
    ctx.break_target_stack.append(end_label)

    groups = (
        [
            c
            for c in body_node.children
            if c.type
            in (JavaNodeType.SWITCH_BLOCK_STATEMENT_GROUP, JavaNodeType.SWITCH_RULE)
        ]
        if body_node
        else []
    )

    for group in groups:
        label_node = next(
            (c for c in group.children if c.type == JavaNodeType.SWITCH_LABEL), None
        )
        body_stmts = [
            c
            for c in group.children
            if c.is_named and c.type != JavaNodeType.SWITCH_LABEL
        ]

        arm_label = ctx.fresh_label("case_arm")
        next_label = ctx.fresh_label("case_next")

        is_default = label_node is not None and not any(
            c.is_named for c in label_node.children
        )

        if label_node and not is_default:
            case_value = next((c for c in label_node.children if c.is_named), None)
            if case_value:
                case_reg = ctx.lower_expr(case_value)
                cmp_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.BINOP,
                    result_reg=cmp_reg,
                    operands=["==", subject_reg, case_reg],
                    node=group,
                )
                ctx.emit(
                    Opcode.BRANCH_IF,
                    operands=[cmp_reg],
                    label=f"{arm_label},{next_label}",
                )
            else:
                ctx.emit(Opcode.BRANCH, label=arm_label)
        else:
            ctx.emit(Opcode.BRANCH, label=arm_label)

        ctx.emit(Opcode.LABEL, label=arm_label)
        has_block = any(s.type == JavaNodeType.BLOCK for s in body_stmts)
        if has_block:
            # Block-form arm: yield_statement inside handles STORE_VAR + BRANCH
            for stmt in body_stmts:
                ctx.lower_stmt(stmt)
        else:
            arm_result = ctx.fresh_reg()
            for stmt in body_stmts:
                arm_result = ctx.lower_expr(stmt)
            ctx.emit(Opcode.DECL_VAR, operands=[result_var, arm_result])
            ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    ctx.break_target_stack.pop()
    ctx.switch_result_stack.pop()
    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def lower_yield_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Java yield_statement inside switch expression block arms.

    ``yield expr;`` stores expr into the enclosing switch expression's
    result variable and branches to the switch end label.
    """
    value_children = [c for c in node.children if c.is_named]
    val_reg = ctx.lower_expr(value_children[0]) if value_children else ctx.fresh_reg()
    result_var = ctx.switch_result_stack[-1]
    end_label = ctx.break_target_stack[-1]
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, val_reg], node=node)
    ctx.emit(Opcode.BRANCH, label=end_label, node=node)


def lower_do_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower do { body } while (condition);"""
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


def lower_assert_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower assert condition; or assert condition : message;"""
    named_children = [c for c in node.children if c.is_named]
    cond_node = named_children[0] if named_children else None
    message_node = named_children[1] if len(named_children) > 1 else None

    arg_regs: list[str] = []
    if cond_node:
        arg_regs.append(ctx.lower_expr(cond_node))
    if message_node:
        arg_regs.append(ctx.lower_expr(message_node))

    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=ctx.fresh_reg(),
        operands=["assert"] + arg_regs,
        node=node,
    )


def lower_labeled_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower label: statement — just lower the inner statement."""
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) >= 2:
        ctx.lower_stmt(named_children[-1])


def lower_synchronized_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower synchronized(expr) { body } — lower lock expr and body."""
    body_node = node.child_by_field_name("body")
    lock_node = next(
        (c for c in node.children if c.type == JavaNodeType.PARENTHESIZED_EXPRESSION),
        None,
    )
    if lock_node:
        ctx.lower_expr(lock_node)
    if body_node:
        ctx.lower_block(body_node)


def lower_throw(ctx: TreeSitterEmitContext, node) -> None:
    lower_raise_or_throw(ctx, node, keyword="throw")


def lower_try(ctx: TreeSitterEmitContext, node) -> None:
    # Lower try-with-resources declarations before the try body
    resources_node = node.child_by_field_name("resources")
    scope_entered = resources_node is not None and ctx.block_scoped
    if scope_entered:
        ctx.enter_block_scope()
    if resources_node:
        for resource in resources_node.children:
            if resource.type == JavaNodeType.RESOURCE:
                _lower_resource_decl(ctx, resource)

    body_node = node.child_by_field_name("body")
    catch_clauses: list[dict] = []
    finally_node = None
    for child in node.children:
        if child.type == JavaNodeType.CATCH_CLAUSE:
            param_node = next(
                (
                    c
                    for c in child.children
                    if c.type == JavaNodeType.CATCH_FORMAL_PARAMETER
                ),
                None,
            )
            exc_var = None
            exc_type = None
            if param_node:
                name_node = param_node.child_by_field_name("name")
                exc_var = ctx.node_text(name_node) if name_node else None
                type_nodes = [
                    c for c in param_node.children if c.is_named and c != name_node
                ]
                if type_nodes:
                    exc_type = ctx.node_text(type_nodes[0])
            catch_body = child.child_by_field_name("body")
            catch_clauses.append(
                {"body": catch_body, "variable": exc_var, "type": exc_type}
            )
        elif child.type == JavaNodeType.FINALLY_CLAUSE:
            finally_node = child.child_by_field_name("body") or next(
                (c for c in child.children if c.type == JavaNodeType.BLOCK),
                None,
            )
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node)

    if scope_entered:
        ctx.exit_block_scope()


def _lower_resource_decl(ctx: TreeSitterEmitContext, resource) -> None:
    """Lower a try-with-resources resource: ``Type name = expr``."""
    name_node = resource.child_by_field_name("name")
    value_node = resource.child_by_field_name("value")
    raw_name = ctx.node_text(name_node) if name_node else "__resource"
    var_name = ctx.declare_block_var(raw_name)
    val_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    ctx.emit(Opcode.DECL_VAR, operands=[var_name, val_reg], node=resource)


def lower_explicit_constructor_invocation(ctx: TreeSitterEmitContext, node) -> None:
    """Lower super(...) or this(...) explicit constructor calls.

    ``this(args)`` is lowered as CALL_METHOD on the current object so that
    the VM dispatches to the matching ``__init__`` overload with ``this``
    properly set via params[0] in the child frame.
    """
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    arg_regs = extract_call_args_unwrap(ctx, args_node) if args_node else []

    first_named = next(
        (c for c in node.children if c.type in (JavaNodeType.SUPER, JavaNodeType.THIS)),
        None,
    )
    target_name = first_named.type if first_named else "super"

    if target_name == JavaNodeType.THIS:
        this_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=ctx.fresh_reg(),
            operands=[this_reg, "__init__"] + arg_regs,
            node=node,
        )
    else:
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=ctx.fresh_reg(),
            operands=[target_name] + arg_regs,
            node=node,
        )
