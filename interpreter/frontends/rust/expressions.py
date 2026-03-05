"""Rust-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import lower_const_literal

logger = logging.getLogger(__name__)


def lower_field_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower field_expression: value.field -> LOAD_FIELD."""
    value_node = node.child_by_field_name("value")
    field_node = node.child_by_field_name("field")
    if value_node is None or field_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(value_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def lower_reference_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower &expr or &mut expr -> UNOP '&'."""
    children = [c for c in node.children if c.type not in ("&", "mut")]
    inner = children[0] if children else node
    inner_reg = ctx.lower_expr(inner)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=reg,
        operands=["&", inner_reg],
        node=node,
    )
    return reg


def lower_deref_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower *expr -> UNOP '*'."""
    children = [c for c in node.children if c.type != "*"]
    inner = children[0] if children else node
    inner_reg = ctx.lower_expr(inner)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=reg,
        operands=["*", inner_reg],
        node=node,
    )
    return reg


def lower_if_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust if expression (value-producing)."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("consequence")
    alt_node = node.child_by_field_name("alternative")

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")
    result_var = f"__if_result_{ctx.label_counter}"

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
    true_reg = lower_block_expr(ctx, body_node)
    ctx.emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        false_reg = ctx.lower_expr(alt_node)
        ctx.emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def lower_expr_stmt_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Unwrap expression_statement to its inner expression."""
    named = [c for c in node.children if c.is_named]
    if named:
        return ctx.lower_expr(named[0])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_else_clause(ctx: TreeSitterEmitContext, node) -> str:
    """Lower else_clause by extracting its inner block or expression."""
    named = [c for c in node.children if c.is_named]
    if named:
        return ctx.lower_expr(named[0])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_return_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust return expression (value-producing)."""
    children = [c for c in node.children if c.type != "return"]
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
        Opcode.RETURN,
        operands=[val_reg],
        node=node,
    )
    return val_reg


def lower_match_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower match expression as if/else chain returning last arm value."""
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")

    val_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    result_var = f"__match_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("match_end")

    arms = [c for c in body_node.children if c.type == "match_arm"] if body_node else []

    for arm in arms:
        arm_pattern = next((c for c in arm.children if c.type == "match_pattern"), None)
        arm_body_children = [
            c
            for c in arm.children
            if c.type not in ("match_pattern", "=>", ",", "fat_arrow") and c.is_named
        ]
        arm_label = ctx.fresh_label("match_arm")
        next_label = ctx.fresh_label("match_next")

        if arm_pattern:
            pattern_reg = ctx.lower_expr(arm_pattern)
            cond_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=cond_reg,
                operands=["==", val_reg, pattern_reg],
                node=arm,
            )
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{arm_label},{next_label}",
            )
        else:
            ctx.emit(Opcode.BRANCH, label=arm_label)

        ctx.emit(Opcode.LABEL, label=arm_label)
        arm_result = ctx.fresh_reg()
        if arm_body_children:
            arm_result = ctx.lower_expr(arm_body_children[0])
        else:
            ctx.emit(
                Opcode.CONST,
                result_reg=arm_result,
                operands=[ctx.constants.none_literal],
            )
        ctx.emit(Opcode.STORE_VAR, operands=[result_var, arm_result])
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def lower_block_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower a block `{ ... }` as an expression (last expr is value)."""
    children = [
        c
        for c in node.children
        if c.type not in ("{", "}", ";")
        and c.type not in ctx.constants.comment_types
        and c.type not in ctx.constants.noise_types
        and c.is_named
    ]
    if not children:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=reg,
            operands=[ctx.constants.none_literal],
        )
        return reg
    for child in children[:-1]:
        ctx.lower_stmt(child)
    return ctx.lower_expr(children[-1])


def lower_closure_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust closure expression |params| body."""
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = f"__closure_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        _lower_closure_params(ctx, params_node)

    if body_node:
        result_reg = ctx.lower_expr(body_node)
        ctx.emit(Opcode.RETURN, operands=[result_reg])
    else:
        none_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[ctx.constants.default_return_value],
        )
        ctx.emit(Opcode.RETURN, operands=[none_reg])

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
    )
    return reg


def _lower_closure_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower closure parameters (|a, b| style)."""
    from interpreter.frontends.rust.declarations import lower_rust_param

    for child in params_node.children:
        if child.type in ("|", ",", ":"):
            continue
        if child.type == "identifier":
            pname = ctx.node_text(child)
            ctx.emit(
                Opcode.SYMBOLIC,
                result_reg=ctx.fresh_reg(),
                operands=[f"{constants.PARAM_PREFIX}{pname}"],
                node=child,
            )
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[pname, f"%{ctx.reg_counter - 1}"],
            )
        elif child.type == "parameter":
            lower_rust_param(ctx, child)


def lower_struct_instantiation(ctx: TreeSitterEmitContext, node) -> str:
    """Lower struct_expression: Point { x: 1, y: 2 }."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    struct_name = ctx.node_text(name_node) if name_node else "Struct"

    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[struct_name],
        node=node,
    )

    if body_node:
        for child in body_node.children:
            if child.type == "field_initializer":
                field_name_node = child.child_by_field_name("field")
                field_val_node = child.child_by_field_name("value")
                if field_name_node and field_val_node:
                    val_reg = ctx.lower_expr(field_val_node)
                    ctx.emit(
                        Opcode.STORE_FIELD,
                        operands=[
                            obj_reg,
                            ctx.node_text(field_name_node),
                            val_reg,
                        ],
                    )
                elif field_name_node:
                    # Shorthand: `Point { x, y }` means `Point { x: x, y: y }`
                    from interpreter.frontends.common.expressions import (
                        lower_identifier,
                    )

                    val_reg = lower_identifier(ctx, field_name_node)
                    ctx.emit(
                        Opcode.STORE_FIELD,
                        operands=[
                            obj_reg,
                            ctx.node_text(field_name_node),
                            val_reg,
                        ],
                    )
    return obj_reg


def lower_macro_invocation(ctx: TreeSitterEmitContext, node) -> str:
    """Lower macro_invocation: println!(...) -> CALL_FUNCTION."""
    macro_name = ctx.node_text(node).split("!")[0] + "!"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=[macro_name],
        node=node,
    )
    return reg


def lower_index_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower index_expression: arr[idx] -> LOAD_INDEX."""
    children = [c for c in node.children if c.is_named]
    if len(children) < 2:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(children[0])
    idx_reg = ctx.lower_expr(children[1])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDEX,
        result_reg=reg,
        operands=[obj_reg, idx_reg],
        node=node,
    )
    return reg


def lower_tuple_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower tuple_expression: (a, b, c) -> NEW_ARRAY."""
    elems = [c for c in node.children if c.type not in ("(", ")", ",")]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=arr_reg,
        operands=["tuple", size_reg],
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
    return arr_reg


def lower_try_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `expr?` as CALL_FUNCTION("try_unwrap", inner)."""
    inner = next(
        (c for c in node.children if c.type != "?" and c.is_named),
        None,
    )
    inner_reg = ctx.lower_expr(inner) if inner else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["try_unwrap", inner_reg],
        node=node,
    )
    return reg


def lower_await_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `expr.await` as CALL_FUNCTION("await", inner)."""
    inner = next(
        (c for c in node.children if c.type not in (".", "await") and c.is_named),
        None,
    )
    inner_reg = ctx.lower_expr(inner) if inner else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["await", inner_reg],
        node=node,
    )
    return reg


def lower_type_cast_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `expr as Type` as CALL_FUNCTION('as', expr, type_name)."""
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_const_literal(ctx, node)
    expr_reg = ctx.lower_expr(named_children[0])
    type_name = ctx.node_text(named_children[-1])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["as", expr_reg, type_name],
        node=node,
    )
    return reg


def lower_scoped_identifier(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `HashMap::new`, `Shape::Circle` as LOAD_VAR with qualified name."""
    full_name = "::".join(
        ctx.node_text(c) for c in node.children if c.type == "identifier"
    )
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_VAR,
        result_reg=reg,
        operands=[full_name],
        node=node,
    )
    return reg


def lower_range_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `0..10` or `0..=10` as CALL_FUNCTION("range", start, end)."""
    named = [c for c in node.children if c.is_named]
    start_reg = ctx.lower_expr(named[0]) if len(named) > 0 else ctx.fresh_reg()
    end_reg = ctx.lower_expr(named[1]) if len(named) > 1 else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["range", start_reg, end_reg],
        node=node,
    )
    return reg


def lower_loop_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower while/loop/for in expression position (returns unit)."""
    ctx.lower_stmt(node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_continue_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower continue in expression position."""
    from interpreter.frontends.common.control_flow import lower_continue

    lower_continue(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_break_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower break in expression position."""
    from interpreter.frontends.common.control_flow import lower_break

    lower_break(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower assignment_expression: left = right (value-producing)."""
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    val_reg = ctx.lower_expr(right)
    lower_rust_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_compound_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower compound_assignment_expr: left += right."""
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    op_node = node.child_by_field_name("operator")
    op_text = ctx.node_text(op_node).rstrip("=") if op_node else "+"
    lhs_reg = ctx.lower_expr(left)
    rhs_reg = ctx.lower_expr(right)
    result = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=result,
        operands=[op_text, lhs_reg, rhs_reg],
        node=node,
    )
    lower_rust_store_target(ctx, left, result, node)
    return result


def lower_tuple_struct_pattern(ctx: TreeSitterEmitContext, node) -> str:
    """Lower tuple_struct_pattern like Some(x) or Message::Write(text)."""
    type_node = next(
        (
            c
            for c in node.children
            if c.type in ("identifier", "scoped_identifier", "type_identifier")
        ),
        None,
    )
    variant_name = ctx.node_text(type_node) if type_node else ctx.node_text(node)
    variant_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=variant_reg,
        operands=[variant_name],
        node=node,
    )
    # Extract inner bindings (identifiers inside parentheses)
    inner_ids = [
        c
        for c in node.children
        if c.is_named
        and c.type not in ("identifier", "scoped_identifier", "type_identifier")
    ]
    for i, child in enumerate(inner_ids):
        child_reg = ctx.lower_expr(child)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(
            Opcode.STORE_INDEX,
            operands=[variant_reg, idx_reg, child_reg],
        )
    return variant_reg


def lower_generic_function(ctx: TreeSitterEmitContext, node) -> str:
    """Lower a.parse::<i32>() -- strip type params, lower as identifier."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_let_condition(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `let Some(val) = opt` -- lower value, destructure pattern, return cond."""
    pattern_node = node.child_by_field_name("pattern")
    value_node = node.child_by_field_name("value")
    val_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()

    if pattern_node:
        pattern_reg = ctx.lower_expr(pattern_node)
        cond_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=cond_reg,
            operands=["==", val_reg, pattern_reg],
            node=node,
        )
        return cond_reg
    return val_reg


def lower_struct_pattern_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower struct_pattern like Message::Move { x, y } as pattern value."""
    type_node = next(
        (
            c
            for c in node.children
            if c.type in ("type_identifier", "scoped_type_identifier")
        ),
        None,
    )
    type_name = ctx.node_text(type_node) if type_node else ctx.node_text(node)
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[f"struct_pattern:{type_name}"],
        node=node,
    )
    # Extract field bindings
    field_patterns = [c for c in node.children if c.type == "field_pattern"]
    for fp in field_patterns:
        name_node = next(
            (
                ch
                for ch in fp.children
                if ch.type in ("field_identifier", "shorthand_field_identifier")
            ),
            None,
        )
        if name_node:
            field_name = ctx.node_text(name_node)
            key_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=key_reg, operands=[field_name])
            val_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[field_name])
            ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
    return obj_reg


# ── Rust-specific store target ────────────────────────────────────────


def lower_rust_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Rust-specific store target handling field_expression and index_expression."""
    if target.type == "identifier":
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == "field_expression":
        value_node = target.child_by_field_name("value")
        field_node = target.child_by_field_name("field")
        if value_node and field_node:
            obj_reg = ctx.lower_expr(value_node)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, ctx.node_text(field_node), val_reg],
                node=parent_node,
            )
    elif target.type == "index_expression":
        children = [c for c in target.children if c.is_named]
        if len(children) >= 2:
            obj_reg = ctx.lower_expr(children[0])
            idx_reg = ctx.lower_expr(children[1])
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, idx_reg, val_reg],
                node=parent_node,
            )
    elif target.type == "dereference_expression":
        inner_children = [c for c in target.children if c.type != "*"]
        if inner_children:
            ctx.lower_expr(inner_children[0])
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[f"*{ctx.node_text(inner_children[0])}", val_reg],
                node=parent_node,
            )
    else:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
