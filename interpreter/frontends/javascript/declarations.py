"""JavaScript-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.javascript.expressions import lower_js_params
from interpreter.frontends.javascript.node_types import JavaScriptNodeType as JSN
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.common.declarations import make_class_ref
from interpreter.type_expr import ScalarType, metatype


def lower_js_var_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower lexical_declaration / variable_declaration, handling destructuring."""
    for child in node.children:
        if child.type != JSN.VARIABLE_DECLARATOR:
            continue
        name_node = child.child_by_field_name(ctx.constants.func_name_field)
        value_node = child.child_by_field_name("value")
        if name_node is None:
            continue

        if name_node.type == JSN.OBJECT_PATTERN and value_node:
            val_reg = ctx.lower_expr(value_node)
            _lower_object_destructure(ctx, name_node, val_reg, node)
        elif name_node.type == JSN.ARRAY_PATTERN and value_node:
            val_reg = ctx.lower_expr(value_node)
            _lower_array_destructure(ctx, name_node, val_reg, node)
        elif value_node:
            var_name = ctx.declare_block_var(ctx.node_text(name_node))
            val_reg = ctx.lower_expr(value_node)
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[var_name, val_reg],
                node=node,
            )
        else:
            var_name = ctx.declare_block_var(ctx.node_text(name_node))
            val_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[var_name, val_reg],
                node=node,
            )


def _lower_object_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower { a, b } = obj or { x: localX } = obj, including ...rest."""
    extracted_keys: list[str] = []
    rest_child = None

    for child in pattern_node.children:
        if child.type == JSN.SHORTHAND_PROPERTY_IDENTIFIER_PATTERN:
            prop_name = ctx.node_text(child)
            extracted_keys.append(prop_name)
            field_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.LOAD_FIELD,
                result_reg=field_reg,
                operands=[val_reg, prop_name],
                node=child,
            )
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[prop_name, field_reg],
                node=parent_node,
            )
        elif child.type == JSN.PAIR_PATTERN:
            key_node = child.child_by_field_name("key")
            value_child = child.child_by_field_name("value")
            if key_node and value_child:
                key_name = ctx.node_text(key_node)
                local_name = ctx.node_text(value_child)
                extracted_keys.append(key_name)
                field_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.LOAD_FIELD,
                    result_reg=field_reg,
                    operands=[val_reg, key_name],
                    node=child,
                )
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[local_name, field_reg],
                    node=parent_node,
                )
        elif child.type == JSN.REST_PATTERN:
            rest_child = child

    if rest_child is not None:
        rest_name = _extract_rest_name(rest_child)
        if rest_name:
            key_regs = [_const_reg(ctx, key) for key in extracted_keys]
            rest_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_FUNCTION,
                result_reg=rest_reg,
                operands=["object_rest", val_reg, *key_regs],
                node=rest_child,
            )
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[rest_name, rest_reg],
                node=parent_node,
            )


def _const_reg(ctx: TreeSitterEmitContext, value: str) -> str:
    """Emit a CONST and return the register holding the value."""
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=reg, operands=[value])
    return reg


def _extract_rest_name(child) -> str | None:
    """Extract the identifier name from a rest_pattern node, or None if not rest."""
    if child.type != JSN.REST_PATTERN:
        return None
    id_child = next((c for c in child.children if c.type == JSN.IDENTIFIER), None)
    return id_child.text.decode("utf-8") if id_child else None


def _lower_array_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower [a, b] = arr, including rest patterns like [a, ...rest] = arr."""
    named_children = [c for c in pattern_node.children if c.is_named]
    for i, child in enumerate(named_children):
        rest_name = _extract_rest_name(child)
        if rest_name is not None:
            # ...rest — slice from index i onward
            start_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=start_reg, operands=[str(i)])
            rest_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_FUNCTION,
                result_reg=rest_reg,
                operands=["slice", val_reg, start_reg],
                node=child,
            )
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[rest_name, rest_reg],
                node=parent_node,
            )
        else:
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
                Opcode.DECL_VAR,
                operands=[ctx.node_text(child), elem_reg],
                node=parent_node,
            )


def _extract_js_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class name from a JS class declaration (single inheritance)."""
    heritage = next((c for c in node.children if c.type == JSN.CLASS_HERITAGE), None)
    if heritage is None:
        return []
    parent_id = next((c for c in heritage.children if c.type == JSN.IDENTIFIER), None)
    return [ctx.node_text(parent_id)] if parent_id else []


def lower_js_class_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower anonymous class expression: `class { ... }` or `class Name { ... }`.

    Like lower_js_class_def but returns a register (expression position)
    and handles missing name by generating a synthetic one.
    """
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = (
        ctx.node_text(name_node) if name_node else f"__anon_class_{ctx.label_counter}"
    )
    parents = _extract_js_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    if body_node:
        for child in body_node.children:
            if child.type == JSN.METHOD_DEFINITION:
                _lower_method_def(ctx, child)
            elif child.type == JSN.CLASS_STATIC_BLOCK:
                lower_class_static_block(ctx, child)
            elif child.type == JSN.FIELD_DEFINITION:
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
        operands=[make_class_ref(class_name, class_label, parents)],
    )
    ctx.seed_register_type(cls_reg, metatype(ScalarType(class_name)))
    return cls_reg


def lower_js_class_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node)
    parents = _extract_js_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    if body_node:
        for child in body_node.children:
            if child.type == JSN.METHOD_DEFINITION:
                _lower_method_def(ctx, child)
            elif child.type == JSN.CLASS_STATIC_BLOCK:
                lower_class_static_block(ctx, child)
            elif child.type == JSN.FIELD_DEFINITION:
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
        operands=[make_class_ref(class_name, class_label, parents)],
    )
    ctx.seed_var_type(class_name, metatype(ScalarType(class_name)))
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])


def _emit_this_param(ctx: TreeSitterEmitContext) -> None:
    """Emit ``SYMBOLIC param:this`` + ``STORE_VAR this`` for instance methods."""
    param_reg = ctx.fresh_reg()
    class_type = ScalarType(ctx._current_class_name)
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=param_reg,
        operands=[f"{constants.PARAM_PREFIX}this"],
    )
    ctx.seed_register_type(param_reg, class_type)
    ctx.seed_param_type(constants.PARAM_THIS, class_type)
    ctx.emit(
        Opcode.DECL_VAR,
        operands=[constants.PARAM_THIS, param_reg],
    )
    ctx.seed_var_type(constants.PARAM_THIS, class_type)


def _has_static_modifier(node) -> bool:
    """Return True if *node* has a ``static`` child token."""
    return any(c.type == JSN.STATIC for c in node.children)


def _lower_method_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

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
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_js_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function_declaration using JS-specific param handling."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

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
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_export_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `export ...` by unwrapping and lowering the inner declaration."""
    for child in node.children:
        if child.is_named and child.type not in (JSN.EXPORT, JSN.DEFAULT):
            ctx.lower_stmt(child)


def lower_class_static_block(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `static { ... }` inside a class body."""
    body_node = node.child_by_field_name("body")
    if body_node:
        ctx.lower_block(body_node)
        return
    # Fallback: lower all named children as statements
    for child in node.children:
        if child.is_named and child.type not in (JSN.STATIC,):
            ctx.lower_stmt(child)
