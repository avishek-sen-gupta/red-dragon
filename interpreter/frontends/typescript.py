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
from interpreter.frontends.type_extraction import normalize_type_hint
from interpreter.frontends.context import TreeSitterEmitContext


class TypeScriptFrontend(JavaScriptFrontend):
    """Lowers TypeScript AST to IR. Extends JavaScriptFrontend, skipping type annotations."""

    def _build_constants(self) -> GrammarConstants:
        js_constants = super()._build_constants()
        return GrammarConstants(
            attr_object_field=js_constants.attr_object_field,
            attr_attribute_field=js_constants.attr_attribute_field,
            attribute_node_type=js_constants.attribute_node_type,
            subscript_value_field=js_constants.subscript_value_field,
            subscript_index_field=js_constants.subscript_index_field,
            comment_types=frozenset({"comment"}),
            noise_types=frozenset({"\n"}),
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
                "type_identifier": common_expr.lower_identifier,
                "predefined_type": common_expr.lower_const_literal,
                "as_expression": lower_as_expression,
                "non_null_expression": lower_non_null_expr,
                "satisfies_expression": lower_satisfies_expr,
                "arrow_function": lower_ts_arrow_function,
                "function": lower_ts_function_expression,
                "function_expression": lower_ts_function_expression,
                "generator_function": lower_ts_function_expression,
                "generator_function_declaration": lower_ts_function_def,
            }
        )
        return dispatch

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        dispatch = super()._build_stmt_dispatch()
        dispatch["function_declaration"] = lower_ts_function_def
        dispatch["class_declaration"] = lower_ts_class_def
        dispatch.update(
            {
                "interface_declaration": lower_interface_decl,
                "enum_declaration": lower_enum_decl,
                "type_alias_declaration": lambda ctx, node: None,
                "export_statement": lower_ts_export_statement,
                "import_statement": lambda ctx, node: None,
                "abstract_class_declaration": lower_ts_class_def,
                "public_field_definition": lower_ts_field_definition,
                "abstract_method_signature": lower_ts_abstract_method,
                "internal_module": lower_ts_internal_module,
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
    name_node = node.child_by_field_name("name")
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
    body_node = node.child_by_field_name("body")
    if body_node:
        for i, child in enumerate(c for c in body_node.children if c.is_named):
            member_name_node = child.child_by_field_name("name")
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
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
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
    name_node = node.child_by_field_name("name")
    if name_node is None:
        name_node = next(
            (c for c in node.children if c.type == "property_identifier"),
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
        if child.is_named and child.type != "export":
            ctx.lower_stmt(child)


def lower_ts_class_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower class_declaration using TS-specific param handling for methods."""
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
                _lower_ts_method_def(ctx, child)
            elif child.type == "class_static_block":
                from interpreter.frontends.javascript.declarations import (
                    lower_class_static_block,
                )

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


def _lower_ts_method_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower method_definition using TS-specific param handling."""
    from interpreter.frontends.javascript.declarations import (
        _emit_this_param,
        _has_static_modifier,
    )

    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

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
    name_node = node.child_by_field_name("name")
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
    body_node = node.child_by_field_name("body")
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
    if child.type in ("(", ")", ",", ":", "type_annotation"):
        return
    if child.type == "required_parameter":
        pname_node = child.child_by_field_name("pattern")
        if pname_node is None:
            pname_node = next(
                (c for c in child.children if c.type == "identifier"), None
            )
        if pname_node:
            pname = ctx.node_text(pname_node)
            type_hint = _extract_ts_type_hint(ctx, child)
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
        return
    if child.type == "optional_parameter":
        pname_node = child.child_by_field_name("pattern")
        if pname_node is None:
            pname_node = next(
                (c for c in child.children if c.type == "identifier"), None
            )
        if pname_node:
            pname = ctx.node_text(pname_node)
            type_hint = _extract_ts_type_hint(ctx, child)
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
        return
    # Fall back to JS param handling
    from interpreter.frontends.javascript.expressions import lower_js_param

    lower_js_param(ctx, child)


def lower_ts_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        lower_ts_param(ctx, child)


def lower_ts_arrow_function(ctx: TreeSitterEmitContext, node) -> str:
    """Lower arrow function using TS-specific param handling."""
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = f"__arrow_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        if params_node.type == "identifier":
            lower_ts_param(ctx, params_node)
        else:
            lower_ts_params(ctx, params_node)

    if body_node:
        if body_node.type == "statement_block":
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
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

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
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
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
    ctx.emit(Opcode.STORE_VAR, operands=[func_name, func_reg])
