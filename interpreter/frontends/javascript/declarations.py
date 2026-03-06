"""JavaScript-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.javascript.expressions import lower_js_params
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)


def lower_js_var_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower lexical_declaration / variable_declaration, handling destructuring."""
    for child in node.children:
        if child.type != "variable_declarator":
            continue
        name_node = child.child_by_field_name("name")
        value_node = child.child_by_field_name("value")
        if name_node is None:
            continue

        if name_node.type == "object_pattern" and value_node:
            val_reg = ctx.lower_expr(value_node)
            _lower_object_destructure(ctx, name_node, val_reg, node)
        elif name_node.type == "array_pattern" and value_node:
            val_reg = ctx.lower_expr(value_node)
            _lower_array_destructure(ctx, name_node, val_reg, node)
        elif value_node:
            val_reg = ctx.lower_expr(value_node)
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[ctx.node_text(name_node), val_reg],
                node=node,
            )
        else:
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


def _lower_object_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower { a, b } = obj or { x: localX } = obj."""
    for child in pattern_node.children:
        if child.type == "shorthand_property_identifier_pattern":
            prop_name = ctx.node_text(child)
            field_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.LOAD_FIELD,
                result_reg=field_reg,
                operands=[val_reg, prop_name],
                node=child,
            )
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[prop_name, field_reg],
                node=parent_node,
            )
        elif child.type == "pair_pattern":
            key_node = child.child_by_field_name("key")
            value_child = child.child_by_field_name("value")
            if key_node and value_child:
                key_name = ctx.node_text(key_node)
                local_name = ctx.node_text(value_child)
                field_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.LOAD_FIELD,
                    result_reg=field_reg,
                    operands=[val_reg, key_name],
                    node=child,
                )
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[local_name, field_reg],
                    node=parent_node,
                )


def _lower_array_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower [a, b] = arr."""
    for i, child in enumerate(c for c in pattern_node.children if c.is_named):
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        elem_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[val_reg, idx_reg],
            node=child,
        )
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(child), elem_reg],
            node=parent_node,
        )


def lower_js_class_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    class_name = ctx.node_text(name_node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    if body_node:
        for child in body_node.children:
            if child.type == "method_definition":
                _lower_method_def(ctx, child)
            elif child.type == "class_static_block":
                lower_class_static_block(ctx, child)
            elif child.type == "field_definition":
                from interpreter.frontends.javascript.expressions import (
                    lower_js_field_definition,
                )

                lower_js_field_definition(ctx, child)
            elif child.is_named:
                ctx.lower_stmt(child)

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


def _has_static_modifier(node) -> bool:
    """Return True if *node* has a ``static`` child token."""
    return any(c.type == "static" for c in node.children)


def _lower_method_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return.lstrip(": "), ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if not _has_static_modifier(node):
        _emit_this_param(ctx)

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
    ctx.emit(Opcode.STORE_VAR, operands=[func_name, func_reg])


def lower_js_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function_declaration using JS-specific param handling."""
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return.lstrip(": "), ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

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
    ctx.emit(Opcode.STORE_VAR, operands=[func_name, func_reg])


def lower_export_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `export ...` by unwrapping and lowering the inner declaration."""
    for child in node.children:
        if child.is_named and child.type not in ("export", "default"):
            ctx.lower_stmt(child)


def lower_class_static_block(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `static { ... }` inside a class body."""
    body_node = node.child_by_field_name("body")
    if body_node:
        ctx.lower_block(body_node)
        return
    # Fallback: lower all named children as statements
    for child in node.children:
        if child.is_named and child.type not in ("static",):
            ctx.lower_stmt(child)
