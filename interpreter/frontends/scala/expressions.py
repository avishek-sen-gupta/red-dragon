"""Scala-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import (
    lower_const_literal,
    lower_interpolated_string_parts,
    lower_call_impl,
)
from interpreter.frontends.scala.node_types import ScalaNodeType as NT


def lower_scala_call(ctx: TreeSitterEmitContext, node) -> str:
    """Lower call_expression, unwrapping generic_function to its inner function.

    In Scala, foo[Int](x) parses as call_expression(generic_function(foo, [Int]), (x)).
    We unwrap the generic_function to expose the raw function node (identifier or
    field_expression) so that lower_call_impl can dispatch correctly.
    """
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    unwrapped_func = (
        func_node.child_by_field_name("function")
        if func_node and func_node.type == NT.GENERIC_FUNCTION
        else func_node
    )
    return lower_call_impl(ctx, unwrapped_func, args_node, node)


def lower_field_expr(ctx: TreeSitterEmitContext, node) -> str:
    value_node = node.child_by_field_name(ctx.constants.attr_object_field)
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
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    val_reg = ctx.lower_expr(right)
    lower_scala_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_scala_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == NT.IDENTIFIER:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == NT.FIELD_EXPRESSION:
        value_node = target.child_by_field_name(ctx.constants.attr_object_field)
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
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

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
    if body_node.type == NT.BLOCK:
        return lower_block_expr(ctx, body_node)
    return ctx.lower_expr(body_node)


def lower_match_expr(ctx: TreeSitterEmitContext, node) -> str:
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")

    val_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    result_var = f"__match_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("match_end")

    clauses = (
        [c for c in body_node.children if c.type == NT.CASE_CLAUSE] if body_node else []
    )

    for clause in clauses:
        pattern_node = clause.child_by_field_name("pattern")
        body_child = clause.child_by_field_name("body")

        arm_label = ctx.fresh_label("case_arm")
        next_label = ctx.fresh_label("case_next")

        if pattern_node and pattern_node.type == NT.WILDCARD:
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
        if c.type not in (NT.LBRACE, NT.RBRACE, NT.SEMICOLON)
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
    children = [c for c in node.children if c.type != NT.RETURN]
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
    elems = [c for c in node.children if c.type not in (NT.LPAREN, NT.RPAREN, NT.COMMA)]
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
        (c for c in node.children if c.type == NT.BINDINGS),
        None,
    )
    if bindings_node:
        for child in bindings_node.children:
            if child.type == NT.BINDING:
                id_node = next(
                    (c for c in child.children if c.type == NT.IDENTIFIER),
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
        and c.type != NT.BINDINGS
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
        (c for c in node.children if c.type == NT.INTERPOLATED_STRING),
        None,
    )
    if interp_string is None:
        return lower_const_literal(ctx, node)
    return lower_scala_interpolated_string_body(ctx, interp_string)


def lower_scala_interpolated_string_body(ctx: TreeSitterEmitContext, node) -> str:
    """Lower interpolated_string, extracting literal gaps and interpolation children."""
    interpolations = [c for c in node.children if c.type == NT.INTERPOLATION]
    if not interpolations:
        return lower_const_literal(ctx, node)

    parts: list[str] = []
    content_start = node.start_byte + 1  # skip opening "
    content_end = node.end_byte - 1  # skip closing "

    for child in node.children:
        if child.type == NT.DOUBLE_QUOTE:
            continue
        if child.type == NT.INTERPOLATION:
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
    children = [c for c in node.children if c.type != NT.THROW and c.is_named]
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
    """Lower case class pattern like Circle(r) or pkg.Circle(r) in match arms."""
    type_node = next(
        (
            c
            for c in node.children
            if c.type in (NT.TYPE_IDENTIFIER, NT.IDENTIFIER, NT.STABLE_TYPE_IDENTIFIER)
        ),
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
        if c.is_named
        and c.type not in (NT.TYPE_IDENTIFIER, NT.IDENTIFIER, NT.STABLE_TYPE_IDENTIFIER)
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
    elems = [
        c
        for c in node.children
        if c.type not in (NT.LPAREN, NT.RPAREN, NT.COMMA) and c.is_named
    ]
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
            (c for c in node.children if c.type == NT.OPERATOR_IDENTIFIER),
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


def lower_generic_function(ctx: TreeSitterEmitContext, node) -> str:
    """Lower generic_function: foo[Int] -> delegate to the inner function expression.

    The generic_function node has field 'function' (the base expression) and
    field 'type_arguments' (the type params, which we strip). When used as a
    callee in call_expression, the call_expression handler manages the call;
    here we just resolve the function reference by lowering the inner expression.
    """
    func_node = node.child_by_field_name("function")
    return ctx.lower_expr(func_node)


def lower_postfix_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower postfix_expression: 'list sorted' -> CALL_METHOD(sorted) on list with 0 args.

    The node has two named children: child[0] is the receiver, child[1] is the method name.
    """
    named_children = [c for c in node.children if c.is_named]
    receiver_node = named_children[0]
    method_node = named_children[1]
    obj_reg = ctx.lower_expr(receiver_node)
    method_name = ctx.node_text(method_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_METHOD,
        result_reg=reg,
        operands=[obj_reg, method_name],
        node=node,
    )
    return reg


def lower_stable_type_identifier(ctx: TreeSitterEmitContext, node) -> str:
    """Lower stable_type_identifier: pkg.MyClass -> LOAD_VAR(pkg), LOAD_FIELD(MyClass).

    The node has named children: identifier(s) separated by '.', ending with type_identifier.
    Lower as a chain of LOAD_FIELD operations on the base identifier.
    """
    named_children = [c for c in node.children if c.is_named]
    result = ctx.lower_expr(named_children[0])
    for child in named_children[1:]:
        field_name = ctx.node_text(child)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[result, field_name],
            node=node,
        )
        result = reg
    return result


def lower_case_clause_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower case_clause in expression context -- lower the body."""
    body_node = node.child_by_field_name("body")
    if body_node:
        return _lower_body_as_expr(ctx, body_node)
    return lower_const_literal(ctx, node)
