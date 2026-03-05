"""Kotlin-specific declaration lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_child,
    normalize_type_hint,
)

# -- property declaration ----------------------------------------------


def _extract_property_name(ctx: TreeSitterEmitContext, var_decl_node) -> str:
    """Extract name from variable_declaration -> simple_identifier."""
    id_node = next(
        (c for c in var_decl_node.children if c.type == "simple_identifier"),
        None,
    )
    return ctx.node_text(id_node) if id_node else "__unknown"


def _find_property_value(ctx: TreeSitterEmitContext, node):
    """Find the value expression after '=' in a property_declaration."""
    found_eq = False
    for child in node.children:
        if found_eq and child.is_named:
            return child
        if ctx.node_text(child) == "=":
            found_eq = True
    return None


def _lower_multi_variable_destructure(
    ctx: TreeSitterEmitContext, multi_var_node, parent_node
) -> None:
    """Lower `val (a, b) = expr` -- emit LOAD_INDEX + STORE_VAR per element."""
    value_node = _find_property_value(ctx, parent_node)
    if value_node:
        val_reg = ctx.lower_expr(value_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.none_literal],
        )

    var_decls = [c for c in multi_var_node.children if c.type == "variable_declaration"]
    for i, var_decl in enumerate(var_decls):
        var_name = _extract_property_name(ctx, var_decl)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        elem_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[val_reg, idx_reg],
            node=var_decl,
        )
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[var_name, elem_reg],
            node=parent_node,
        )


def lower_property_decl(ctx: TreeSitterEmitContext, node) -> None:
    multi_var_decl = next(
        (c for c in node.children if c.type == "multi_variable_declaration"),
        None,
    )

    if multi_var_decl is not None:
        _lower_multi_variable_destructure(ctx, multi_var_decl, node)
        return

    var_decl = next(
        (c for c in node.children if c.type == "variable_declaration"),
        None,
    )
    var_name = _extract_property_name(ctx, var_decl) if var_decl else "__unknown"

    # Extract type from the variable_declaration child
    raw_type = (
        extract_type_from_child(ctx, var_decl, ("user_type", "nullable_type"))
        if var_decl
        else ""
    )
    type_hint = normalize_type_hint(raw_type, ctx.type_map)

    # Find the value expression: skip keywords, type annotations, '='
    value_node = _find_property_value(ctx, node)

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
        operands=[var_name, val_reg],
        node=node,
        type_hint=type_hint,
    )


# -- function declaration ----------------------------------------------


def _emit_this_param(ctx: TreeSitterEmitContext) -> None:
    """Emit ``SYMBOLIC param:this`` + ``STORE_VAR this`` for instance methods."""
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=ctx.fresh_reg(),
        operands=[f"{constants.PARAM_PREFIX}this"],
    )
    ctx.emit(
        Opcode.STORE_VAR,
        operands=["this", f"%{ctx.reg_counter - 1}"],
    )


def _lower_kotlin_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        if child.type == "parameter":
            id_node = next(
                (c for c in child.children if c.type == "simple_identifier"),
                None,
            )
            if id_node:
                pname = ctx.node_text(id_node)
                raw_type = extract_type_from_child(
                    ctx, child, ("user_type", "nullable_type")
                )
                type_hint = normalize_type_hint(raw_type, ctx.type_map)
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


def _lower_function_body(ctx: TreeSitterEmitContext, body_node) -> None:
    """Lower function_body which wraps the actual block or expression."""
    for child in body_node.children:
        if child.type in ("{", "}", "="):
            continue
        if child.is_named:
            ctx.lower_stmt(child)


def lower_function_decl(
    ctx: TreeSitterEmitContext, node, inject_this: bool = False
) -> None:
    name_node = next(
        (c for c in node.children if c.type == "simple_identifier"),
        None,
    )
    params_node = next(
        (c for c in node.children if c.type == "function_value_parameters"),
        None,
    )
    body_node = next(
        (c for c in node.children if c.type == "function_body"),
        None,
    )

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_child(ctx, node, ("user_type", "nullable_type"))
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label, type_hint=return_hint)

    if inject_this:
        _emit_this_param(ctx)

    if params_node:
        _lower_kotlin_params(ctx, params_node)

    if body_node:
        _lower_function_body(ctx, body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST, result_reg=none_reg, operands=[ctx.constants.default_return_value]
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


# -- class declaration -------------------------------------------------


def _lower_class_body_with_companions(ctx: TreeSitterEmitContext, node) -> None:
    """Lower class_body, handling companion_object children specially."""
    for child in node.children:
        if not child.is_named:
            continue
        if child.type == "companion_object":
            _lower_companion_object(ctx, child)
        elif child.type == "function_declaration":
            lower_function_decl(ctx, child, inject_this=True)
        else:
            ctx.lower_stmt(child)


def _lower_companion_object(ctx: TreeSitterEmitContext, node) -> None:
    """Lower companion object by lowering its class_body child as a block."""
    body_node = next(
        (c for c in node.children if c.type == "class_body"),
        None,
    )
    if body_node:
        ctx.lower_block(body_node)


def _lower_enum_class_body(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum_class_body: create NEW_OBJECT + STORE_VAR for each entry."""
    for child in node.children:
        if child.type == "enum_entry":
            _lower_enum_entry(ctx, child)
        elif child.is_named and child.type not in ("{", "}", ",", ";"):
            ctx.lower_stmt(child)


def _lower_enum_entry(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a single enum_entry as NEW_OBJECT('enum:Name') + STORE_VAR."""
    name_node = next(
        (c for c in node.children if c.type == "simple_identifier"),
        None,
    )
    entry_name = ctx.node_text(name_node) if name_node else "__unknown_enum"
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=reg,
        operands=[f"enum:{entry_name}"],
        node=node,
    )
    ctx.emit(Opcode.STORE_VAR, operands=[entry_name, reg])


def lower_class_decl(ctx: TreeSitterEmitContext, node) -> None:
    name_node = next(
        (c for c in node.children if c.type == "type_identifier"),
        None,
    )
    body_node = next(
        (c for c in node.children if c.type in ("class_body", "enum_class_body")),
        None,
    )
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        if body_node.type == "enum_class_body":
            _lower_enum_class_body(ctx, body_node)
        else:
            _lower_class_body_with_companions(ctx, body_node)
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


# -- object declaration (singleton) ------------------------------------


def lower_object_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower object declaration (Kotlin singleton) like a class."""
    name_node = next(
        (c for c in node.children if c.type == "type_identifier"),
        None,
    )
    body_node = next(
        (c for c in node.children if c.type == "class_body"),
        None,
    )
    obj_name = ctx.node_text(name_node) if name_node else "__anon_object"

    obj_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{obj_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{obj_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=obj_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    inst_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=inst_reg,
        operands=[obj_name],
        node=node,
    )
    ctx.emit(Opcode.STORE_VAR, operands=[obj_name, inst_reg])
