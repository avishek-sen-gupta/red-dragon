"""JavaScript-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import lower_const_literal


def lower_js_subscript(ctx: TreeSitterEmitContext, node) -> str:
    obj_node = node.child_by_field_name("object")
    idx_node = node.child_by_field_name("index")
    if obj_node is None or idx_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    idx_reg = ctx.lower_expr(idx_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDEX,
        result_reg=reg,
        operands=[obj_reg, idx_reg],
        node=node,
    )
    return reg


def lower_js_attribute(ctx: TreeSitterEmitContext, node) -> str:
    obj_node = node.child_by_field_name("object")
    prop_node = node.child_by_field_name("property")
    if obj_node is None or prop_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(prop_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def lower_js_call(ctx: TreeSitterEmitContext, node) -> str:
    func_node = node.child_by_field_name("function")
    args_node = node.child_by_field_name("arguments")
    arg_regs = _extract_js_call_args(ctx, args_node) if args_node else []

    if func_node and func_node.type == "member_expression":
        obj_node = func_node.child_by_field_name("object")
        prop_node = func_node.child_by_field_name("property")
        if obj_node and prop_node:
            obj_reg = ctx.lower_expr(obj_node)
            method_name = ctx.node_text(prop_node)
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_METHOD,
                result_reg=reg,
                operands=[obj_reg, method_name] + arg_regs,
                node=node,
            )
            return reg

    if func_node and func_node.type == "identifier":
        func_name = ctx.node_text(func_node)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[func_name] + arg_regs,
            node=node,
        )
        return reg

    target_reg = ctx.lower_expr(func_node) if func_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_UNKNOWN,
        result_reg=reg,
        operands=[target_reg] + arg_regs,
        node=node,
    )
    return reg


def _extract_js_call_args(ctx: TreeSitterEmitContext, args_node) -> list[str]:
    if args_node is None:
        return []
    return [
        ctx.lower_expr(c)
        for c in args_node.children
        if c.type not in ("(", ")", ",") and c.is_named
    ]


def lower_js_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == "identifier":
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == "member_expression":
        obj_node = target.child_by_field_name("object")
        prop_node = target.child_by_field_name("property")
        if obj_node and prop_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, ctx.node_text(prop_node), val_reg],
                node=parent_node,
            )
    elif target.type == "subscript_expression":
        obj_node = target.child_by_field_name("object")
        idx_node = target.child_by_field_name("index")
        if obj_node and idx_node:
            obj_reg = ctx.lower_expr(obj_node)
            idx_reg = ctx.lower_expr(idx_node)
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


def lower_assignment_expr(ctx: TreeSitterEmitContext, node) -> str:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    val_reg = ctx.lower_expr(right)
    lower_js_store_target(ctx, left, val_reg, node)
    return val_reg


def lower_js_object_literal(ctx: TreeSitterEmitContext, node) -> str:
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=["object"],
        node=node,
    )
    for child in node.children:
        if child.type == "pair":
            key_node = child.child_by_field_name("key")
            val_node = child.child_by_field_name("value")
            if key_node and val_node:
                key_reg = lower_const_literal(ctx, key_node)
                val_reg = ctx.lower_expr(val_node)
                ctx.emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, key_reg, val_reg],
                )
        elif child.type == "shorthand_property_identifier":
            from interpreter.frontends.common.expressions import lower_identifier

            key_reg = lower_const_literal(ctx, child)
            val_reg = lower_identifier(ctx, child)
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, key_reg, val_reg],
            )
    return obj_reg


def lower_arrow_function(ctx: TreeSitterEmitContext, node) -> str:
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = f"__arrow_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        if params_node.type == "identifier":
            lower_js_param(ctx, params_node)
        else:
            lower_js_params(ctx, params_node)

    if body_node:
        if body_node.type == "statement_block":
            ctx.lower_block(body_node)
        else:
            # Expression body: implicit return
            val_reg = ctx.lower_expr(body_node)
            ctx.emit(Opcode.RETURN, operands=[val_reg])

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=func_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
    )
    return func_reg


def lower_ternary(ctx: TreeSitterEmitContext, node) -> str:
    cond_node = node.child_by_field_name("condition")
    true_node = node.child_by_field_name("consequence")
    false_node = node.child_by_field_name("alternative")

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("ternary_true")
    false_label = ctx.fresh_label("ternary_false")
    end_label = ctx.fresh_label("ternary_end")

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{true_label},{false_label}",
    )

    ctx.emit(Opcode.LABEL, label=true_label)
    true_reg = ctx.lower_expr(true_node)
    result_var = f"__ternary_{ctx.label_counter}"
    ctx.emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=false_label)
    false_reg = ctx.lower_expr(false_node)
    ctx.emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    result_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=result_reg, operands=[result_var])
    return result_reg


def lower_new_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `new Foo(args)` -> NEW_OBJECT(class) + CALL_METHOD('constructor', args)."""
    constructor_node = node.child_by_field_name("constructor")
    args_node = node.child_by_field_name("arguments")
    class_name = ctx.node_text(constructor_node) if constructor_node else "Object"
    arg_regs = _extract_js_call_args(ctx, args_node) if args_node else []

    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[class_name],
        node=node,
    )
    ctor_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_METHOD,
        result_reg=ctor_reg,
        operands=[obj_reg, "constructor"] + arg_regs,
        node=node,
    )
    return obj_reg


def lower_await_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `await expr` -> CALL_FUNCTION('await', expr)."""
    children = [c for c in node.children if c.is_named]
    expr_reg = ctx.lower_expr(children[0]) if children else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["await", expr_reg],
        node=node,
    )
    return reg


def lower_yield_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `yield expr` or bare `yield` -> CALL_FUNCTION('yield', expr)."""
    children = [c for c in node.children if c.is_named]
    if children:
        expr_reg = ctx.lower_expr(children[0])
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["yield", expr_reg],
            node=node,
        )
        return reg
    # Bare yield
    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.none_literal],
    )
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["yield", none_reg],
        node=node,
    )
    return reg


def lower_sequence_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `(a, b, c)` -> evaluate all, return last register."""
    children = [c for c in node.children if c.is_named]
    if not children:
        return lower_const_literal(ctx, node)
    last_reg = ctx.lower_expr(children[0])
    for child in children[1:]:
        last_reg = ctx.lower_expr(child)
    return last_reg


def lower_spread_element(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `...expr` -> CALL_FUNCTION('spread', expr)."""
    children = [c for c in node.children if c.is_named]
    expr_reg = ctx.lower_expr(children[0]) if children else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["spread", expr_reg],
        node=node,
    )
    return reg


def lower_function_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower anonymous function expression: same as function_declaration but anonymous."""
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node) if name_node else f"__anon_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        lower_js_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=func_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
    )
    return func_reg


def lower_template_string(ctx: TreeSitterEmitContext, node) -> str:
    """Lower template string, descending into template_substitution children."""
    has_substitution = any(c.type == "template_substitution" for c in node.children)
    if not has_substitution:
        return lower_const_literal(ctx, node)

    # Build by concatenating literal fragments and substitution expressions
    parts: list[str] = []
    for child in node.children:
        if child.type == "template_substitution":
            parts.append(lower_template_substitution(ctx, child))
        elif child.is_named:
            parts.append(ctx.lower_expr(child))
        elif child.type not in ("`",):
            # String fragment
            frag_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=frag_reg,
                operands=[ctx.node_text(child)],
            )
            parts.append(frag_reg)

    if not parts:
        return lower_const_literal(ctx, node)
    result = parts[0]
    for part in parts[1:]:
        new_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=new_reg,
            operands=["+", result, part],
            node=node,
        )
        result = new_reg
    return result


def lower_template_substitution(ctx: TreeSitterEmitContext, node) -> str:
    """Lower ${expr} inside a template string."""
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return lower_const_literal(ctx, node)


def lower_export_clause(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `{ a, b }` export clause — lower inner export_specifiers."""
    last_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=last_reg, operands=[ctx.constants.none_literal])
    for child in node.children:
        if child.is_named:
            last_reg = ctx.lower_expr(child)
    return last_reg


def lower_js_field_definition(ctx: TreeSitterEmitContext, node) -> str:
    """Lower class field: `#privateField = 0` or `name = expr`."""
    property_node = node.child_by_field_name("property")
    value_node = node.child_by_field_name("value")
    field_name = ctx.node_text(property_node) if property_node else ctx.node_text(node)
    if value_node:
        val_reg = ctx.lower_expr(value_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.none_literal],
        )
    ctx.emit(
        Opcode.STORE_VAR,
        operands=[field_name, val_reg],
        node=node,
    )
    # Return val_reg so this can be used in both stmt and expr contexts
    return val_reg


# ── JS param handling ────────────────────────────────────────


def lower_js_param(ctx: TreeSitterEmitContext, child) -> None:
    if child.type in ("(", ")", ","):
        return
    if child.type == "identifier":
        pname = ctx.node_text(child)
    elif child.type in (
        "assignment_pattern",
        "object_pattern",
        "array_pattern",
    ):
        pname = ctx.node_text(child)
    else:
        from interpreter.frontends.common.declarations import extract_param_name

        pname = extract_param_name(ctx, child)
        if pname is None:
            return
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


def lower_js_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        lower_js_param(ctx, child)
