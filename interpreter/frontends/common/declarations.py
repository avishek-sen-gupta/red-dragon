"""Common declaration lowerers — pure functions taking (ctx, node).

Extracted from BaseFrontend: function_def, params, class_def, var_declaration.
"""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)


def lower_function_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map) if raw_return else ""

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label, type_hint=return_hint)

    if params_node:
        lower_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    # Implicit return at end of function
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
    ctx.emit(Opcode.STORE_VAR, operands=[func_name, func_reg])


def lower_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower function parameters. Override for language-specific param shapes."""
    for child in params_node.children:
        lower_param(ctx, child)


def lower_param(ctx: TreeSitterEmitContext, child) -> None:
    """Lower a single function parameter to SYMBOLIC + STORE_VAR."""
    if child.type in ("(", ")", ",", ":", "->"):
        return
    pname = extract_param_name(ctx, child)
    if pname is None:
        return
    raw_type = extract_type_from_field(ctx, child, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map) if raw_type else ""
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=ctx.fresh_reg(),
        operands=[f"{constants.PARAM_PREFIX}{pname}"],
        node=child,
        type_hint=type_hint,
    )
    ctx.emit(
        Opcode.STORE_VAR,
        operands=[pname, f"%{ctx.reg_counter - 1}"],
        type_hint=type_hint,
    )


def extract_param_name(ctx: TreeSitterEmitContext, child) -> str | None:
    """Extract parameter name from a parameter node."""
    if child.type == "identifier":
        return ctx.node_text(child)
    # Try common field names
    for field in ("name", "pattern"):
        name_node = child.child_by_field_name(field)
        if name_node:
            return ctx.node_text(name_node)
    # Try first identifier child
    id_node = next(
        (sub for sub in child.children if sub.type == "identifier"),
        None,
    )
    if id_node:
        return ctx.node_text(id_node)
    return None


def lower_class_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=class_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])


def lower_var_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a variable declaration with name/value fields or declarators."""
    for child in node.children:
        if child.type == "variable_declarator":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                val_reg = ctx.lower_expr(value_node)
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[ctx.node_text(name_node), val_reg],
                    node=node,
                )
            elif name_node:
                # Declaration without initializer
                val_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[ctx.constants.none_literal],
                )
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[ctx.node_text(name_node), val_reg],
                    node=node,
                )
