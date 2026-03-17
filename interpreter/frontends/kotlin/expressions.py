"""Kotlin-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import (
    lower_const_literal,
    lower_identifier,
    lower_interpolated_string_parts,
    lower_update_expr,
)
from interpreter.frontends.kotlin.node_types import KotlinNodeType as KNT

logger = logging.getLogger(__name__)


def lower_kotlin_identifier(ctx: TreeSitterEmitContext, node) -> str:
    """Lower identifier, intercepting 'field' inside property accessor bodies."""
    text = ctx.node_text(node)
    if text == "field" and ctx._accessor_backing_field:
        this_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[this_reg, ctx._accessor_backing_field],
            node=node,
        )
        return reg
    return lower_identifier(ctx, node)


# -- string interpolation ----------------------------------------------


def lower_kotlin_string_literal(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Kotlin string literal, decomposing $var / ${expr} interpolation."""
    has_interpolation = any(
        c.type in (KNT.INTERPOLATED_IDENTIFIER, KNT.INTERPOLATED_EXPRESSION)
        for c in node.children
    )
    if not has_interpolation:
        return lower_const_literal(ctx, node)

    parts: list[str] = []
    for child in node.children:
        if child.type == KNT.STRING_CONTENT:
            frag_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=frag_reg,
                operands=[ctx.node_text(child)],
                node=child,
            )
            parts.append(frag_reg)
        elif child.type == KNT.INTERPOLATED_IDENTIFIER:
            parts.append(lower_identifier(ctx, child))
        elif child.type == KNT.INTERPOLATED_EXPRESSION:
            named = [c for c in child.children if c.is_named]
            if named:
                parts.append(ctx.lower_expr(named[0]))
        # skip punctuation: ", $, ${, }
    return lower_interpolated_string_parts(ctx, parts, node)


# -- call expression ---------------------------------------------------


def _extract_kotlin_args(ctx: TreeSitterEmitContext, args_node) -> list[str]:
    """Extract argument registers from value_arguments -> value_argument."""
    if args_node is None:
        return []
    regs = []
    for child in args_node.children:
        if child.type == KNT.VALUE_ARGUMENT:
            inner = next((gc for gc in child.children if gc.is_named), None)
            if inner:
                regs.append(ctx.lower_expr(inner))
        elif child.is_named and child.type not in ("(", ")", ","):
            regs.append(ctx.lower_expr(child))
    return regs


def _extract_nav_field_name(ctx: TreeSitterEmitContext, node) -> str:
    """Extract the identifier name from a navigation_suffix or plain node.

    ``navigation_suffix`` nodes include the leading dot in their text,
    so we unwrap to the inner ``simple_identifier`` instead.
    """
    if node.type == KNT.NAVIGATION_SUFFIX:
        id_node = next(
            (c for c in node.children if c.type == KNT.SIMPLE_IDENTIFIER), None
        )
        if id_node:
            return ctx.node_text(id_node)
    return ctx.node_text(node)


def lower_kotlin_call(ctx: TreeSitterEmitContext, node) -> str:
    """Lower call_expression: first child is callee, call_suffix has args."""
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_const_literal(ctx, node)

    callee_node = named_children[0]
    call_suffix = next(
        (c for c in node.children if c.type == KNT.CALL_SUFFIX),
        None,
    )

    args_node = None
    if call_suffix:
        args_node = next(
            (c for c in call_suffix.children if c.type == KNT.VALUE_ARGUMENTS),
            None,
        )

    arg_regs = _extract_kotlin_args(ctx, args_node)

    # Method call via navigation_expression
    if callee_node.type == KNT.NAVIGATION_EXPRESSION:
        nav_children = [c for c in callee_node.children if c.is_named]
        if len(nav_children) >= 2:
            obj_reg = ctx.lower_expr(nav_children[0])
            method_name = _extract_nav_field_name(ctx, nav_children[-1])
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_METHOD,
                result_reg=reg,
                operands=[obj_reg, method_name] + arg_regs,
                node=node,
            )
            return reg

    # Plain function call
    if callee_node.type == KNT.SIMPLE_IDENTIFIER:
        func_name = ctx.node_text(callee_node)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[func_name] + arg_regs,
            node=node,
        )
        return reg

    # Dynamic call target
    target_reg = ctx.lower_expr(callee_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_UNKNOWN,
        result_reg=reg,
        operands=[target_reg] + arg_regs,
        node=node,
    )
    return reg


# -- navigation expression (member access) -----------------------------


def lower_navigation_expr(ctx: TreeSitterEmitContext, node) -> str:
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) < 2:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(named_children[0])
    field_name = _extract_nav_field_name(ctx, named_children[-1])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


# -- if expression (value-producing) -----------------------------------


def _lower_control_body(ctx: TreeSitterEmitContext, body_node) -> str:
    """Lower control_structure_body or block, returning last expr reg."""
    if body_node is None:
        reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=reg, operands=[ctx.constants.none_literal])
        return reg
    children = [
        c
        for c in body_node.children
        if c.type not in ("{", "}", ";")
        and c.type not in ctx.constants.comment_types
        and c.type not in ctx.constants.noise_types
        and c.is_named
    ]
    if not children:
        reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=reg, operands=[ctx.constants.none_literal])
        return reg
    # If the sole child is a block node (e.g. `statements`), unwrap it
    if len(children) == 1 and children[0].type in ctx.constants.block_node_types:
        inner = [
            c
            for c in children[0].children
            if c.is_named and c.type not in ctx.constants.comment_types
        ]
        scope_entered = ctx.block_scoped
        if scope_entered:
            ctx.enter_block_scope()
        for child in inner[:-1]:
            ctx.lower_stmt(child)
        # Try lowering last child as expression; if it's a statement-only
        # node (no expr handler), lower as statement and return None
        if inner and inner[-1].type in ctx.expr_dispatch:
            result = ctx.lower_expr(inner[-1])
        elif inner:
            ctx.lower_stmt(inner[-1])
            result = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=result,
                operands=[ctx.constants.none_literal],
            )
        else:
            result = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=result,
                operands=[ctx.constants.none_literal],
            )
        if scope_entered:
            ctx.exit_block_scope()
        return result
    for child in children[:-1]:
        ctx.lower_stmt(child)
    return ctx.lower_expr(children[-1])


def lower_if_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Kotlin if as an expression (returns a value)."""
    children = [c for c in node.children if c.is_named]
    # Children layout: condition, consequence, [alternative]
    cond_node = children[0] if children else None
    body_node = children[1] if len(children) > 1 else None
    alt_node = children[2] if len(children) > 2 else None

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
    true_reg = _lower_control_body(ctx, body_node)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        false_reg = _lower_control_body(ctx, alt_node)
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, false_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


# -- when expression ---------------------------------------------------


def lower_when_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower when(subject) { entries } as an if/else chain.

    Kotlin allows ``when(val x = expr) { }`` where the subject variable
    is scoped to the when expression body.
    """
    subject_node = next(
        (c for c in node.children if c.type == KNT.WHEN_SUBJECT),
        None,
    )

    # Detect when-subject binding: when(val x = expr) { }
    subject_var_decl = (
        next(
            (c for c in subject_node.children if c.type == KNT.VARIABLE_DECLARATION),
            None,
        )
        if subject_node
        else None
    )
    scope_entered = subject_var_decl is not None and ctx.block_scoped
    if scope_entered:
        ctx.enter_block_scope()

    val_reg = ctx.fresh_reg()
    if subject_node:
        if subject_var_decl:
            # Lower the value expression (sibling of variable_declaration)
            value_expr = next(
                (
                    c
                    for c in subject_node.children
                    if c.is_named and c.type != KNT.VARIABLE_DECLARATION
                ),
                None,
            )
            val_reg = ctx.lower_expr(value_expr) if value_expr else ctx.fresh_reg()
            # Bind the subject variable
            name_node = next((c for c in subject_var_decl.children if c.is_named), None)
            raw_name = ctx.node_text(name_node) if name_node else "__when_subject"
            var_name = ctx.declare_block_var(raw_name)
            ctx.emit(Opcode.DECL_VAR, operands=[var_name, val_reg])
        else:
            inner = next((c for c in subject_node.children if c.is_named), None)
            if inner:
                val_reg = ctx.lower_expr(inner)

    result_var = f"__when_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("when_end")

    entries = [c for c in node.children if c.type == KNT.WHEN_ENTRY]
    for entry in entries:
        cond_node = next(
            (c for c in entry.children if c.type == KNT.WHEN_CONDITION),
            None,
        )
        body_children = [
            c
            for c in entry.children
            if c.type not in (KNT.WHEN_CONDITION, "->", ",")
            and c.is_named
            and c.type != KNT.CONTROL_STRUCTURE_BODY
        ]
        body_node = next(
            (c for c in entry.children if c.type == KNT.CONTROL_STRUCTURE_BODY),
            None,
        )

        arm_label = ctx.fresh_label("when_arm")
        next_label = ctx.fresh_label("when_next")

        if cond_node:
            cond_inner = next((c for c in cond_node.children if c.is_named), None)
            if cond_inner:
                pattern_reg = ctx.lower_expr(cond_inner)
                eq_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.BINOP,
                    result_reg=eq_reg,
                    operands=["==", val_reg, pattern_reg],
                    node=entry,
                )
                ctx.emit(
                    Opcode.BRANCH_IF,
                    operands=[eq_reg],
                    label=f"{arm_label},{next_label}",
                )
            else:
                # else branch
                ctx.emit(Opcode.BRANCH, label=arm_label)
        else:
            # else branch (no condition)
            ctx.emit(Opcode.BRANCH, label=arm_label)

        ctx.emit(Opcode.LABEL, label=arm_label)
        if body_node:
            arm_result = _lower_control_body(ctx, body_node)
        elif body_children:
            arm_result = ctx.lower_expr(body_children[0])
        else:
            arm_result = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=arm_result,
                operands=[ctx.constants.none_literal],
            )
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, arm_result])
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])

    if scope_entered:
        ctx.exit_block_scope()

    return reg


# -- statements as expression ------------------------------------------


def lower_statements_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower a ``statements`` node in expression context (last child is value)."""
    children = [c for c in node.children if c.is_named]
    if not children:
        reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=reg, operands=[ctx.constants.none_literal])
        return reg
    for child in children[:-1]:
        ctx.lower_stmt(child)
    return ctx.lower_expr(children[-1])


def lower_loop_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower while/for/do-while in expression position (returns unit)."""
    ctx.lower_stmt(node)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=reg, operands=[ctx.constants.none_literal])
    return reg


# -- assignment as expression ------------------------------------------


def lower_kotlin_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower assignment in expression context (e.g. last expr in block)."""
    from interpreter.frontends.kotlin.control_flow import lower_kotlin_assignment

    lower_kotlin_assignment(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=reg, operands=[ctx.constants.none_literal])
    return reg


# -- jump as expression ------------------------------------------------


def lower_jump_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower jump_expression in expression context (emit + return reg)."""
    from interpreter.frontends.kotlin.control_flow import lower_jump_expr

    lower_jump_expr(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=reg, operands=[ctx.constants.none_literal])
    return reg


# -- postfix expression ------------------------------------------------


def lower_postfix_expr(ctx: TreeSitterEmitContext, node) -> str:
    text = ctx.node_text(node)
    if "++" in text or "--" in text:
        return lower_update_expr(ctx, node)
    if text.endswith("!!"):
        return _lower_not_null_assertion(ctx, node)
    return lower_const_literal(ctx, node)


def _lower_not_null_assertion(ctx: TreeSitterEmitContext, node) -> str:
    """Lower not-null assertion (expr!!) as UNOP('!!', expr)."""
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_const_literal(ctx, node)
    expr_reg = ctx.lower_expr(named_children[0])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=reg,
        operands=["!!", expr_reg],
        node=node,
    )
    return reg


# -- lambda literal ----------------------------------------------------


def lower_lambda_literal(ctx: TreeSitterEmitContext, node) -> str:
    func_name = f"__lambda_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    # Extract lambda parameters: lambda_parameters -> variable_declaration -> simple_identifier
    lambda_params_node = next(
        (c for c in node.children if c.type == KNT.LAMBDA_PARAMETERS),
        None,
    )
    if lambda_params_node:
        for child in lambda_params_node.children:
            if child.type == KNT.VARIABLE_DECLARATION:
                id_node = next(
                    (c for c in child.children if c.type == KNT.SIMPLE_IDENTIFIER),
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
                        Opcode.DECL_VAR,
                        operands=[pname, f"%{ctx.reg_counter - 1}"],
                    )

    # Lambda body children (skip braces, arrow, lambda_parameters)
    body_children = [
        c
        for c in node.children
        if c.type not in ("{", "}", "->")
        and c.is_named
        and c.type != KNT.LAMBDA_PARAMETERS
        and c.type not in ctx.constants.comment_types
    ]
    # Kotlin lambdas implicitly return the last expression.
    # If the body is a `statements` node, lower all but the last child
    # as statements, then return the last expression's value.
    last_returned = False
    if len(body_children) == 1 and body_children[0].type == KNT.STATEMENTS:
        stmts = [
            c
            for c in body_children[0].children
            if c.is_named and c.type not in ctx.constants.comment_types
        ]
        for stmt in stmts[:-1]:
            ctx.lower_stmt(stmt)
        if stmts:
            last_reg = ctx.lower_expr(stmts[-1])
            ctx.emit(Opcode.RETURN, operands=[last_reg])
            last_returned = True
    else:
        for child in body_children:
            ctx.lower_stmt(child)

    if not last_returned:
        none_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[ctx.constants.default_return_value],
        )
        ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=reg)
    return reg


# -- anonymous function expression ------------------------------------


def lower_anonymous_function(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `fun(x: Int): Int { return x * 2 }` as a function definition.

    Structurally similar to lambda_literal but uses function_value_parameters
    and function_body (identical to named function_declaration minus the name).
    """
    func_name = f"__anon_fun_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    # Extract and lower parameters
    params_node = next(
        (c for c in node.children if c.type == KNT.FUNCTION_VALUE_PARAMETERS),
        None,
    )
    if params_node:
        _lower_anon_func_params(ctx, params_node)

    # Lower function body
    body_node = next(
        (c for c in node.children if c.type == KNT.FUNCTION_BODY),
        None,
    )
    expr_reg = _lower_anon_func_body(ctx, body_node) if body_node else ""

    if expr_reg:
        ctx.emit(Opcode.RETURN, operands=[expr_reg])
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
    ctx.emit_func_ref(func_name, func_label, result_reg=reg)
    return reg


def _lower_anon_func_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Emit SYMBOLIC param: + STORE_VAR for each parameter in function_value_parameters."""
    for child in params_node.children:
        if child.type == KNT.PARAMETER:
            id_node = next(
                (c for c in child.children if c.type == KNT.SIMPLE_IDENTIFIER),
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
                    Opcode.DECL_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )


def _lower_anon_func_body(ctx: TreeSitterEmitContext, body_node) -> str:
    """Lower function_body, returning last expression register for expression-bodied funs."""
    last_reg = ""
    for child in body_node.children:
        if child.type in ("{", "}", "="):
            continue
        if child.is_named:
            is_stmt = (
                ctx.stmt_dispatch.get(child.type) is not None
                or child.type in ctx.constants.block_node_types
            )
            if is_stmt:
                ctx.lower_stmt(child)
                last_reg = ""
            else:
                last_reg = ctx.lower_expr(child)
    return last_reg


# -- object literal (anonymous object expression) ------------------------


def lower_object_literal(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `object : Type { ... }` as NEW_OBJECT + body lowering."""
    delegation = next(
        (c for c in node.children if c.type == KNT.DELEGATION_SPECIFIER),
        None,
    )
    body_node = next(
        (c for c in node.children if c.type == KNT.CLASS_BODY),
        None,
    )
    type_name = ctx.node_text(delegation) if delegation else "__anon_object"

    obj_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{type_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{type_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=obj_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    inst_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=inst_reg,
        operands=[type_name],
        node=node,
    )
    return inst_reg


# -- range expression --------------------------------------------------


def lower_range_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `1..10` as CALL_FUNCTION("range", start, end)."""
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


# -- check expression (is / !is) --------------------------------------


def lower_check_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower check_expression (is/!is) as CALL_FUNCTION('is', expr, type_text)."""
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) < 2:
        return lower_const_literal(ctx, node)
    expr_reg = ctx.lower_expr(named_children[0])
    type_text = ctx.node_text(named_children[-1])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["is", expr_reg, type_text],
        node=node,
    )
    return reg


# -- try expression (in expression context) ----------------------------


def lower_try_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower try_expression in expression context (returns a register)."""
    from interpreter.frontends.kotlin.control_flow import lower_try_stmt

    lower_try_stmt(ctx, node)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=reg, operands=[ctx.constants.none_literal])
    return reg


# -- elvis expression (?:) ---------------------------------------------


def _rhs_has_throw(node) -> bool:
    """Check if the RHS of an elvis expression is a throw (jump_expression)."""
    return node.type == KNT.JUMP_EXPRESSION and any(
        c.type == "throw" for c in node.children
    )


def lower_elvis_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `x ?: default` as BINOP or conditional branch (when RHS is throw).

    When the RHS is a throw expression, short-circuit evaluation is required:
    the throw must only execute when the LHS is null.  We emit an if-else
    branch instead of an eager BINOP.
    """
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) < 2:
        return lower_const_literal(ctx, node)

    rhs_node = named_children[-1]

    if _rhs_has_throw(rhs_node):
        return _lower_elvis_with_throw(ctx, node, named_children[0], rhs_node)

    left_reg = ctx.lower_expr(named_children[0])
    right_reg = ctx.lower_expr(rhs_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=reg,
        operands=["?:", left_reg, right_reg],
        node=node,
    )
    return reg


def _lower_elvis_with_throw(
    ctx: TreeSitterEmitContext, node, lhs_node, rhs_node
) -> str:
    """Lower `x ?: throw E()` as conditional: if x != null use x, else throw."""
    left_reg = ctx.lower_expr(lhs_node)

    null_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=null_reg, operands=[ctx.constants.none_literal])

    cond_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cond_reg, operands=["!=", left_reg, null_reg])

    non_null_label = ctx.fresh_label("elvis_non_null")
    throw_label = ctx.fresh_label("elvis_throw")
    end_label = ctx.fresh_label("elvis_end")

    result_var = f"__elvis_result_{ctx.label_counter}"

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{non_null_label},{throw_label}",
        node=node,
    )

    ctx.emit(Opcode.LABEL, label=non_null_label)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, left_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=throw_label)
    ctx.lower_expr(rhs_node)
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


# -- infix expression --------------------------------------------------


_KOTLIN_BITWISE_INFIX: dict[str, str] = {
    "and": "&",
    "or": "|",
    "xor": "^",
    "shl": "<<",
    "shr": ">>",
}


def lower_infix_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `a to b`, `x until y` as CALL_FUNCTION(infix_name, left, right).

    Kotlin bitwise infix functions (and, or, xor, shl, shr) are lowered as
    BINOP with the corresponding operator symbol.
    """
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) < 3:
        return lower_const_literal(ctx, node)
    left_reg = ctx.lower_expr(named_children[0])
    func_name = ctx.node_text(named_children[1])
    right_reg = ctx.lower_expr(named_children[2])
    reg = ctx.fresh_reg()
    bitwise_op = _KOTLIN_BITWISE_INFIX.get(func_name)
    if bitwise_op:
        ctx.emit(
            Opcode.BINOP,
            result_reg=reg,
            operands=[bitwise_op, left_reg, right_reg],
            node=node,
        )
    else:
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[func_name, left_reg, right_reg],
            node=node,
        )
    return reg


# -- indexing expression -----------------------------------------------


def lower_indexing_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `collection[index]` as LOAD_INDEX."""
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(named_children[0])
    # The index is inside indexing_suffix
    suffix_node = next(
        (c for c in node.children if c.type == KNT.INDEXING_SUFFIX),
        None,
    )
    if suffix_node is None:
        return obj_reg
    idx_children = [c for c in suffix_node.children if c.is_named]
    if not idx_children:
        return obj_reg
    idx_reg = ctx.lower_expr(idx_children[0])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDEX,
        result_reg=reg,
        operands=[obj_reg, idx_reg],
        node=node,
    )
    return reg


# -- as expression (type cast) -----------------------------------------


def lower_as_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `expr as Type` as CALL_FUNCTION('as', expr, type_name)."""
    named_children = [c for c in node.children if c.is_named]
    if len(named_children) < 2:
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


# -- type_test (is Type in when) ----------------------------------


def lower_type_test(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `is Type` as CONST(type_name) for pattern matching in when."""
    named_children = [c for c in node.children if c.is_named]
    type_node = named_children[0] if named_children else None
    type_name = ctx.node_text(type_node) if type_node else ctx.node_text(node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[f"is:{type_name}"],
        node=node,
    )
    return reg


# -- store target override for navigation_expression -------------------


def lower_kotlin_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == KNT.SIMPLE_IDENTIFIER:
        text = ctx.node_text(target)
        if text == "field" and ctx._accessor_backing_field:
            this_reg = ctx.fresh_reg()
            ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[this_reg, ctx._accessor_backing_field, val_reg],
                node=parent_node,
            )
            return
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[text, val_reg],
            node=parent_node,
        )
    elif target.type == KNT.NAVIGATION_EXPRESSION:
        named_children = [c for c in target.children if c.is_named]
        if len(named_children) >= 2:
            obj_reg = ctx.lower_expr(named_children[0])
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[
                    obj_reg,
                    _extract_nav_field_name(ctx, named_children[-1]),
                    val_reg,
                ],
                node=parent_node,
            )
        else:
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[ctx.node_text(target), val_reg],
                node=parent_node,
            )
    elif target.type == KNT.INDEXING_EXPRESSION:
        named_children = [c for c in target.children if c.is_named]
        if named_children:
            obj_reg = ctx.lower_expr(named_children[0])
            suffix_node = next(
                (c for c in target.children if c.type == KNT.INDEXING_SUFFIX),
                None,
            )
            if suffix_node:
                idx_children = [c for c in suffix_node.children if c.is_named]
                idx_reg = (
                    ctx.lower_expr(idx_children[0]) if idx_children else ctx.fresh_reg()
                )
            else:
                idx_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, idx_reg, val_reg],
                node=parent_node,
            )
        else:
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[ctx.node_text(target), val_reg],
                node=parent_node,
            )
    elif target.type == KNT.DIRECTLY_ASSIGNABLE_EXPRESSION:
        # Check for indexing: simple_identifier + indexing_suffix
        suffix_node = next(
            (c for c in target.children if c.type == KNT.INDEXING_SUFFIX),
            None,
        )
        nav_suffix = next(
            (c for c in target.children if c.type == KNT.NAVIGATION_SUFFIX),
            None,
        )
        if suffix_node:
            id_node = next(
                (c for c in target.children if c.type == KNT.SIMPLE_IDENTIFIER),
                None,
            )
            obj_reg = ctx.lower_expr(id_node) if id_node else ctx.fresh_reg()
            idx_children = [c for c in suffix_node.children if c.is_named]
            idx_reg = (
                ctx.lower_expr(idx_children[0]) if idx_children else ctx.fresh_reg()
            )
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, idx_reg, val_reg],
                node=parent_node,
            )
        elif nav_suffix:
            # Navigation assignment: this.field = val or obj.field = val
            named_children = [c for c in target.children if c.is_named]
            obj_node = next(
                (c for c in named_children if c.type != KNT.NAVIGATION_SUFFIX),
                None,
            )
            obj_reg = ctx.lower_expr(obj_node) if obj_node else ctx.fresh_reg()
            field_name = _extract_nav_field_name(ctx, nav_suffix)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, field_name, val_reg],
                node=parent_node,
            )
        else:
            # Unwrap the inner node
            inner = next((c for c in target.children if c.is_named), None)
            if inner:
                lower_kotlin_store_target(ctx, inner, val_reg, parent_node)
            else:
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[ctx.node_text(target), val_reg],
                    node=parent_node,
                )
    else:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )


# -- P1 gap handlers ------------------------------------------------------


def lower_callable_reference(ctx: TreeSitterEmitContext, node) -> str:
    """Lower ::functionName — emit LOAD_VAR for the referenced function."""
    named_children = [c for c in node.children if c.is_named]
    func_name = (
        ctx.node_text(named_children[-1]) if named_children else ctx.node_text(node)
    )
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[func_name], node=node)
    return reg


def lower_spread_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower *array — just lower the inner expression (the spread target)."""
    named_children = [c for c in node.children if c.is_named]
    return (
        ctx.lower_expr(named_children[0])
        if named_children
        else lower_const_literal(ctx, node)
    )
