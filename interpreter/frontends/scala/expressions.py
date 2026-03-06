"""Scala-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import (
    lower_const_literal,
    lower_interpolated_string_parts,
)


def lower_field_expr(ctx: TreeSitterEmitContext, node) -> str:
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


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    val_reg = ctx.lower_expr(right)
    lower_scala_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_scala_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
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
    else:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )


def lower_if_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower if as a value-producing expression."""
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("consequence")
    alt_node = node.child_by_field_name("alternative")

    cond_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
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
    true_reg = _lower_body_as_expr(ctx, body_node)
    ctx.emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        false_reg = _lower_body_as_expr(ctx, alt_node)
        ctx.emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def _lower_body_as_expr(ctx: TreeSitterEmitContext, body_node) -> str:
    """Lower a body node as an expression, returning the last expression's reg."""
    if body_node is None:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=reg,
            operands=[ctx.constants.none_literal],
        )
        return reg
    if body_node.type == "block":
        return lower_block_expr(ctx, body_node)
    return ctx.lower_expr(body_node)


def lower_match_expr(ctx: TreeSitterEmitContext, node) -> str:
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")

    val_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    result_var = f"__match_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("match_end")

    clauses = (
        [c for c in body_node.children if c.type == "case_clause"] if body_node else []
    )

    for clause in clauses:
        pattern_node = clause.child_by_field_name("pattern")
        body_child = clause.child_by_field_name("body")

        arm_label = ctx.fresh_label("case_arm")
        next_label = ctx.fresh_label("case_next")

        if pattern_node and pattern_node.type == "wildcard":
            ctx.emit(Opcode.BRANCH, label=arm_label)
        elif pattern_node:
            pattern_reg = ctx.lower_expr(pattern_node)
            cond_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.BINOP,
                result_reg=cond_reg,
                operands=["==", val_reg, pattern_reg],
                node=clause,
            )
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{arm_label},{next_label}",
            )
        else:
            ctx.emit(Opcode.BRANCH, label=arm_label)

        ctx.emit(Opcode.LABEL, label=arm_label)
        if body_child:
            arm_result = _lower_body_as_expr(ctx, body_child)
        else:
            arm_result = ctx.fresh_reg()
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


def lower_loop_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower while/for/do-while in expression position (returns unit)."""
    ctx.lower_stmt(node)
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


def lower_return_expr(ctx: TreeSitterEmitContext, node) -> str:
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


def lower_wildcard(ctx: TreeSitterEmitContext, node) -> str:
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=reg,
        operands=["wildcard:_"],
        node=node,
    )
    return reg


def lower_tuple_expr(ctx: TreeSitterEmitContext, node) -> str:
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


def lower_lambda_expr(ctx: TreeSitterEmitContext, node) -> str:
    func_name = f"__lambda_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    # Extract lambda parameters: bindings -> binding -> identifier
    bindings_node = next(
        (c for c in node.children if c.type == "bindings"),
        None,
    )
    if bindings_node:
        for child in bindings_node.children:
            if child.type == "binding":
                id_node = next(
                    (c for c in child.children if c.type == "identifier"),
                    None,
                )
                if id_node:
                    pname = ctx.node_text(id_node)
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

    # Lambda body: lower all named children except bindings.
    # Scala lambdas implicitly return the last expression.
    named_children = [
        c
        for c in node.children
        if c.is_named
        and c.type != "bindings"
        and c.type not in ctx.constants.comment_types
    ]
    for child in named_children[:-1]:
        ctx.lower_stmt(child)
    if named_children:
        last_reg = ctx.lower_expr(named_children[-1])
        ctx.emit(Opcode.RETURN, operands=[last_reg])
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


def lower_new_expr(ctx: TreeSitterEmitContext, node) -> str:
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        type_name = ctx.node_text(named_children[0])
    else:
        type_name = "Object"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=[type_name],
        node=node,
    )
    ctx.seed_register_type(reg, type_name)
    return reg


def lower_symbolic_node(ctx: TreeSitterEmitContext, node) -> str:
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=reg,
        operands=[f"{node.type}:{ctx.node_text(node)[:60]}"],
        node=node,
    )
    return reg


def lower_scala_interpolated_string(ctx: TreeSitterEmitContext, node) -> str:
    """Lower interpolated_string_expression: s"..." / f"..." / raw"..."."""
    interp_string = next(
        (c for c in node.children if c.type == "interpolated_string"),
        None,
    )
    if interp_string is None:
        return lower_const_literal(ctx, node)
    return lower_scala_interpolated_string_body(ctx, interp_string)


def lower_scala_interpolated_string_body(ctx: TreeSitterEmitContext, node) -> str:
    """Lower interpolated_string, extracting literal gaps and interpolation children."""
    interpolations = [c for c in node.children if c.type == "interpolation"]
    if not interpolations:
        return lower_const_literal(ctx, node)

    parts: list[str] = []
    content_start = node.start_byte + 1  # skip opening "
    content_end = node.end_byte - 1  # skip closing "

    for child in node.children:
        if child.type == '"':
            continue
        if child.type == "interpolation":
            # Emit literal gap before this interpolation
            gap_text = ctx.source[content_start : child.start_byte].decode("utf-8")
            if gap_text:
                frag_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=frag_reg,
                    operands=[gap_text],
                    node=node,
                )
                parts.append(frag_reg)
            # Lower the interpolation expression
            named = [c for c in child.children if c.is_named]
            if named:
                parts.append(ctx.lower_expr(named[0]))
            content_start = child.end_byte

    # Trailing literal after last interpolation
    trailing = ctx.source[content_start:content_end].decode("utf-8")
    if trailing:
        frag_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=frag_reg,
            operands=[trailing],
            node=node,
        )
        parts.append(frag_reg)

    return lower_interpolated_string_parts(ctx, parts, node)


def lower_try_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower try_expression in expression context (returns a register)."""
    from interpreter.frontends.scala.control_flow import lower_try_stmt

    lower_try_stmt(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
    )
    return reg


def lower_throw_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower throw_expression: throw expr -> lower expr, emit THROW, return reg."""
    children = [c for c in node.children if c.type != "throw" and c.is_named]
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
    return val_reg


def lower_case_class_pattern(ctx: TreeSitterEmitContext, node) -> str:
    """Lower case class pattern like Circle(r) in match arms."""
    type_node = next(
        (c for c in node.children if c.type in ("type_identifier", "identifier")),
        None,
    )
    class_name = ctx.node_text(type_node) if type_node else ctx.node_text(node)

    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[f"pattern:{class_name}"],
        node=node,
    )
    # Extract inner bindings
    inner_bindings = [
        c
        for c in node.children
        if c.is_named and c.type not in ("type_identifier", "identifier")
    ]
    for i, child in enumerate(inner_bindings):
        child_reg = ctx.lower_expr(child)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, idx_reg, child_reg])
    return obj_reg


def lower_typed_pattern(ctx: TreeSitterEmitContext, node) -> str:
    """Lower typed pattern `i: Int` -> lower the identifier, ignore type."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_guard(ctx: TreeSitterEmitContext, node) -> str:
    """Lower guard clause `if condition` in match -> lower the condition."""
    named_children = [c for c in node.children if c.is_named]
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_tuple_pattern_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower (a, b) pattern in match as tuple literal."""
    elems = [c for c in node.children if c.type not in ("(", ")", ",") and c.is_named]
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


def lower_infix_pattern(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `head :: tail` infix pattern as BINOP(::, head, tail)."""
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) >= 2:
        left_reg = ctx.lower_expr(named_children[0])
        right_reg = ctx.lower_expr(named_children[-1])
        op_node = next(
            (c for c in node.children if c.type == "operator_identifier"),
            None,
        )
        op = ctx.node_text(op_node) if op_node else "::"
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=reg,
            operands=[op, left_reg, right_reg],
            node=node,
        )
        return reg
    if named_children:
        return ctx.lower_expr(named_children[0])
    return lower_const_literal(ctx, node)


def lower_case_clause_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower case_clause in expression context -- lower the body."""
    body_node = node.child_by_field_name("body")
    if body_node:
        return _lower_body_as_expr(ctx, body_node)
    return lower_const_literal(ctx, node)
