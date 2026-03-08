"""TypeScriptFrontend — tree-sitter TypeScript AST -> IR lowering.

Extends JavaScriptFrontend, adding TS-specific node handlers and
skipping type annotations.
"""

from __future__ import annotations

from typing import Callable

from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.typescript_node_types import TypeScriptNodeType
from interpreter.frontends.common.declarations import make_class_ref


class TypeScriptFrontend(JavaScriptFrontend):
    """Lowers TypeScript AST to IR. Extends JavaScriptFrontend, skipping type annotations."""

    BLOCK_SCOPED = True

    def _build_constants(self) -> GrammarConstants:
        js_constants = super()._build_constants()
        return GrammarConstants(
            attr_object_field=js_constants.attr_object_field,
            attr_attribute_field=js_constants.attr_attribute_field,
            attribute_node_type=js_constants.attribute_node_type,
            subscript_value_field=js_constants.subscript_value_field,
            subscript_index_field=js_constants.subscript_index_field,
            comment_types=frozenset({TypeScriptNodeType.COMMENT}),
            noise_types=frozenset({TypeScriptNodeType.NEWLINE_CHAR}),
            block_node_types=js_constants.block_node_types,
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "number": "Float",
            "string": "String",
            "boolean": "Bool",
            "void": "Any",
            "any": "Any",
            "undefined": "Any",
            "null": "Any",
            "never": "Any",
            "object": "Object",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        dispatch = super()._build_expr_dispatch()
        dispatch.update(
            {
                TypeScriptNodeType.TYPE_IDENTIFIER: common_expr.lower_identifier,
                TypeScriptNodeType.PREDEFINED_TYPE: common_expr.lower_const_literal,
                TypeScriptNodeType.AS_EXPRESSION: lower_as_expression,
                TypeScriptNodeType.NON_NULL_EXPRESSION: lower_non_null_expr,
                TypeScriptNodeType.SATISFIES_EXPRESSION: lower_satisfies_expr,
                TypeScriptNodeType.ARROW_FUNCTION: lower_ts_arrow_function,
                TypeScriptNodeType.FUNCTION: lower_ts_function_expression,
                TypeScriptNodeType.FUNCTION_EXPRESSION: lower_ts_function_expression,
                TypeScriptNodeType.GENERATOR_FUNCTION: lower_ts_function_expression,
                TypeScriptNodeType.GENERATOR_FUNCTION_DECLARATION: lower_ts_function_def,
            }
        )
        return dispatch

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        dispatch = super()._build_stmt_dispatch()
        dispatch[TypeScriptNodeType.FUNCTION_DECLARATION] = lower_ts_function_def
        dispatch[TypeScriptNodeType.CLASS_DECLARATION] = lower_ts_class_def
        dispatch.update(
            {
                TypeScriptNodeType.INTERFACE_DECLARATION: lower_interface_decl,
                TypeScriptNodeType.ENUM_DECLARATION: lower_enum_decl,
                TypeScriptNodeType.TYPE_ALIAS_DECLARATION: lambda ctx, node: None,
                TypeScriptNodeType.EXPORT_STATEMENT: lower_ts_export_statement,
                TypeScriptNodeType.IMPORT_STATEMENT: lambda ctx, node: None,
                TypeScriptNodeType.ABSTRACT_CLASS_DECLARATION: lower_ts_class_def,
                TypeScriptNodeType.PUBLIC_FIELD_DEFINITION: lower_ts_field_definition,
                TypeScriptNodeType.ABSTRACT_METHOD_SIGNATURE: lower_ts_abstract_method,
                TypeScriptNodeType.INTERNAL_MODULE: lower_ts_internal_module,
            }
        )
        return dispatch


# ── TS-specific expression lowerers (pure functions) ─────────────


def lower_as_expression(ctx: TreeSitterEmitContext, node) -> str:
    # x as Type -> just lower x, ignore the type
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return common_expr.lower_const_literal(ctx, node)


def lower_non_null_expr(ctx: TreeSitterEmitContext, node) -> str:
    # x! -> just lower x
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return common_expr.lower_const_literal(ctx, node)


def lower_satisfies_expr(ctx: TreeSitterEmitContext, node) -> str:
    children = [c for c in node.children if c.is_named]
    if children:
        return ctx.lower_expr(children[0])
    return common_expr.lower_const_literal(ctx, node)


# ── TS-specific statement lowerers (pure functions) ──────────────


def lower_interface_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower interface_declaration as NEW_OBJECT with STORE_INDEX per member."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    if not name_node:
        return
    iface_name = ctx.node_text(name_node)
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[f"interface:{iface_name}"],
        node=node,
    )
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    if body_node:
        for i, child in enumerate(c for c in body_node.children if c.is_named):
            member_name_node = child.child_by_field_name(ctx.constants.func_name_field)
            member_name = (
                ctx.node_text(member_name_node)
                if member_name_node
                else ctx.node_text(child).split(":")[0].strip()
            )
            key_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
            val_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
            ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
    ctx.emit(Opcode.STORE_VAR, operands=[iface_name, obj_reg])


def lower_enum_decl(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    if name_node:
        enum_name = ctx.node_text(name_node)
        obj_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[f"enum:{enum_name}"],
            node=node,
        )
        if body_node:
            for i, child in enumerate(c for c in body_node.children if c.is_named):
                member_name = ctx.node_text(child).split("=")[0].strip()
                key_reg = ctx.fresh_reg()
                ctx.emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
                val_reg = ctx.fresh_reg()
                ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
                ctx.emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, key_reg, val_reg],
                )
        ctx.emit(Opcode.STORE_VAR, operands=[enum_name, obj_reg])


def lower_ts_field_definition(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `public name: type` or `public name = expr` as STORE_VAR."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    if name_node is None:
        name_node = next(
            (
                c
                for c in node.children
                if c.type == TypeScriptNodeType.PROPERTY_IDENTIFIER
            ),
            None,
        )
    if name_node is None:
        return
    field_name = ctx.node_text(name_node)
    value_node = node.child_by_field_name("value")
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


def lower_ts_export_statement(ctx: TreeSitterEmitContext, node) -> None:
    for child in node.children:
        if child.is_named and child.type != TypeScriptNodeType.EXPORT:
            ctx.lower_stmt(child)


def _extract_ts_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class name from a TS class declaration."""
    heritage = next(
        (c for c in node.children if c.type == TypeScriptNodeType.CLASS_HERITAGE),
        None,
    )
    if heritage is None:
        return []
    id_types = (TypeScriptNodeType.IDENTIFIER, TypeScriptNodeType.TYPE_IDENTIFIER)
    return [
        ctx.node_text(c)
        for clause in heritage.children
        if clause.type == "extends_clause"
        for c in clause.children
        if c.type in id_types
    ]


def lower_ts_class_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower class_declaration using TS-specific param handling for methods."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node)
    parents = _extract_ts_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    if body_node:
        for child in body_node.children:
            if child.type == TypeScriptNodeType.METHOD_DEFINITION:
                _lower_ts_method_def(ctx, child)
            elif child.type == TypeScriptNodeType.CLASS_STATIC_BLOCK:
                from interpreter.frontends.javascript.declarations import (
                    lower_class_static_block,
                )

                lower_class_static_block(ctx, child)
            elif child.type == TypeScriptNodeType.FIELD_DEFINITION:
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
    ctx.emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])


def _lower_ts_method_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower method_definition using TS-specific param handling."""
    from interpreter.frontends.javascript.declarations import (
        _emit_this_param,
        _has_static_modifier,
    )

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
        lower_ts_params(ctx, params_node)

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


def lower_ts_abstract_method(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `abstract speak(): string` as a function stub."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    func_name = ctx.node_text(name_node) if name_node else "__abstract"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

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


def lower_ts_internal_module(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `namespace Geometry { ... }` -- descend into body."""
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    if body_node:
        ctx.lower_block(body_node)


# ── TS-specific param handling ───────────────────────────────────


def _extract_ts_type_hint(ctx: TreeSitterEmitContext, param_node) -> str:
    """Extract type hint from a TS parameter's type_annotation field."""
    type_ann = param_node.child_by_field_name("type")
    if type_ann is None:
        return ""
    # type_annotation contains `: <type>` — find the first named non-colon child
    type_child = next(
        (c for c in type_ann.children if c.is_named),
        None,
    )
    raw = ctx.node_text(type_child) if type_child else ""
    return normalize_type_hint(raw, ctx.type_map)


def lower_ts_param(ctx: TreeSitterEmitContext, child) -> None:
    """Lower a single TS parameter, extracting type annotations."""
    if child.type in (
        TypeScriptNodeType.OPEN_PAREN,
        TypeScriptNodeType.CLOSE_PAREN,
        TypeScriptNodeType.COMMA,
        TypeScriptNodeType.COLON,
        TypeScriptNodeType.TYPE_ANNOTATION,
    ):
        return
    if child.type == TypeScriptNodeType.REQUIRED_PARAMETER:
        pname_node = child.child_by_field_name("pattern")
        if pname_node is None:
            pname_node = next(
                (c for c in child.children if c.type == TypeScriptNodeType.IDENTIFIER),
                None,
            )
        if pname_node:
            pname = ctx.node_text(pname_node)
            type_hint = _extract_ts_type_hint(ctx, child)
            sym_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.SYMBOLIC,
                result_reg=sym_reg,
                operands=[f"{constants.PARAM_PREFIX}{pname}"],
                node=child,
            )
            ctx.seed_register_type(sym_reg, type_hint)
            ctx.seed_param_type(pname, type_hint)
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[pname, f"%{ctx.reg_counter - 1}"],
            )
            ctx.seed_var_type(pname, type_hint)
        return
    if child.type == TypeScriptNodeType.OPTIONAL_PARAMETER:
        pname_node = child.child_by_field_name("pattern")
        if pname_node is None:
            pname_node = next(
                (c for c in child.children if c.type == TypeScriptNodeType.IDENTIFIER),
                None,
            )
        if pname_node:
            pname = ctx.node_text(pname_node)
            type_hint = _extract_ts_type_hint(ctx, child)
            sym_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.SYMBOLIC,
                result_reg=sym_reg,
                operands=[f"{constants.PARAM_PREFIX}{pname}"],
                node=child,
            )
            ctx.seed_register_type(sym_reg, type_hint)
            ctx.seed_param_type(pname, type_hint)
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[pname, f"%{ctx.reg_counter - 1}"],
            )
            ctx.seed_var_type(pname, type_hint)
        return
    # Fall back to JS param handling
    from interpreter.frontends.javascript.expressions import lower_js_param

    lower_js_param(ctx, child)


def lower_ts_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        lower_ts_param(ctx, child)


def lower_ts_arrow_function(ctx: TreeSitterEmitContext, node) -> str:
    """Lower arrow function using TS-specific param handling."""
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = f"__arrow_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        if params_node.type == TypeScriptNodeType.IDENTIFIER:
            lower_ts_param(ctx, params_node)
        else:
            lower_ts_params(ctx, params_node)

    if body_node:
        if body_node.type == TypeScriptNodeType.STATEMENT_BLOCK:
            ctx.lower_block(body_node)
        else:
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


def lower_ts_function_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower anonymous function expression using TS-specific param handling."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else f"__anon_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        lower_ts_params(ctx, params_node)

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


def lower_ts_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function_declaration using TS-specific param handling."""
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
        lower_ts_params(ctx, params_node)

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
