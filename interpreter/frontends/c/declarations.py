"""C-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext

logger = logging.getLogger(__name__)


def extract_declarator_name(ctx: TreeSitterEmitContext, decl_node) -> str:
    """Extract the variable name from a declarator, handling pointer declarators."""
    if decl_node.type == "identifier":
        return ctx.node_text(decl_node)
    # pointer_declarator, array_declarator, etc.
    inner = decl_node.child_by_field_name("declarator")
    if inner:
        return extract_declarator_name(ctx, inner)
    # Fallback: first identifier child
    id_node = next((c for c in decl_node.children if c.type == "identifier"), None)
    if id_node:
        return ctx.node_text(id_node)
    return ctx.node_text(decl_node)


def _extract_struct_type(ctx: TreeSitterEmitContext, node) -> str:
    """Return the struct type name if *node* has a struct_specifier, else ''."""
    for child in node.children:
        if child.type == "struct_specifier":
            type_node = child.child_by_field_name("name")
            if type_node is None:
                type_node = next(
                    (c for c in child.children if c.type == "type_identifier"),
                    None,
                )
            if type_node:
                return ctx.node_text(type_node)
    return ""


def lower_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a C declaration: type declarator(s) with optional initializers."""
    struct_type = _extract_struct_type(ctx, node)
    raw_type = extract_type_from_field(ctx, node, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)
    for child in node.children:
        if child.type == "init_declarator":
            _lower_init_declarator(
                ctx, child, struct_type=struct_type, type_hint=type_hint
            )
        elif child.type == "identifier":
            var_name = ctx.node_text(child)
            if struct_type:
                val_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CALL_FUNCTION,
                    result_reg=val_reg,
                    operands=[struct_type],
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
                operands=[var_name, val_reg],
                node=node,
                type_hint=type_hint,
            )


def _lower_init_declarator(
    ctx: TreeSitterEmitContext, node, struct_type: str = "", type_hint: str = ""
) -> None:
    """Lower init_declarator (fields: declarator, value)."""
    decl_node = node.child_by_field_name("declarator")
    value_node = node.child_by_field_name("value")

    var_name = extract_declarator_name(ctx, decl_node) if decl_node else "__anon"

    if value_node:
        val_reg = ctx.lower_expr(value_node)
    elif struct_type:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=val_reg,
            operands=[struct_type],
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
        operands=[var_name, val_reg],
        node=node,
        type_hint=type_hint,
    )


def _find_function_declarator(node):
    """Recursively find function_declarator inside pointer/other declarators."""
    if node.type == "function_declarator":
        return node
    for child in node.children:
        result = _find_function_declarator(child)
        if result:
            return result
    return None


def lower_c_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower C function parameters (parameter_declaration nodes)."""
    for child in params_node.children:
        if child.type == "parameter_declaration":
            decl_node = child.child_by_field_name("declarator")
            if decl_node:
                pname = extract_declarator_name(ctx, decl_node)
                raw_type = extract_type_from_field(ctx, child, "type")
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


def lower_function_def_c(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function_definition with nested function_declarator."""
    declarator_node = node.child_by_field_name("declarator")
    body_node = node.child_by_field_name("body")

    func_name = "__anon"
    params_node = None

    if declarator_node:
        if declarator_node.type == "function_declarator":
            name_node = declarator_node.child_by_field_name("declarator")
            params_node = declarator_node.child_by_field_name("parameters")
            func_name = (
                extract_declarator_name(ctx, name_node) if name_node else "__anon"
            )
        else:
            func_decl = _find_function_declarator(declarator_node)
            if func_decl:
                name_node = func_decl.child_by_field_name("declarator")
                params_node = func_decl.child_by_field_name("parameters")
                func_name = (
                    extract_declarator_name(ctx, name_node) if name_node else "__anon"
                )
            else:
                func_name = extract_declarator_name(ctx, declarator_node)

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        lower_c_params(ctx, params_node)

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


def lower_struct_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower struct_specifier as class."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")

    if name_node is None and body_node is None:
        return

    struct_name = ctx.node_text(name_node) if name_node else "__anon_struct"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{struct_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{struct_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        lower_struct_body(ctx, body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=struct_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[struct_name, cls_reg])


def lower_struct_body(ctx: TreeSitterEmitContext, node) -> None:
    """Lower struct field_declaration_list."""
    for child in node.children:
        if child.type == "field_declaration":
            lower_struct_field(ctx, child)
        elif child.is_named and child.type not in ("{", "}"):
            ctx.lower_stmt(child)


def lower_struct_field(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a struct field declaration as STORE_FIELD on this."""
    declarators = [
        c for c in node.children if c.type in ("field_identifier", "identifier")
    ]
    for decl in declarators:
        fname = ctx.node_text(decl)
        this_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
        default_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=default_reg,
            operands=["0"],
            node=node,
        )
        ctx.emit(
            Opcode.STORE_FIELD,
            operands=[this_reg, fname, default_reg],
            node=node,
        )


def lower_enum_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum_specifier as NEW_OBJECT + STORE_FIELD per enumerator."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")

    if name_node is None and body_node is None:
        return

    enum_name = ctx.node_text(name_node) if name_node else "__anon_enum"

    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[f"enum:{enum_name}"],
        node=node,
    )

    if body_node:
        enumerators = [c for c in body_node.children if c.type == "enumerator"]
        for i, enumerator in enumerate(enumerators):
            name_child = enumerator.child_by_field_name("name")
            value_child = enumerator.child_by_field_name("value")
            member_name = ctx.node_text(name_child) if name_child else f"__enum_{i}"
            if value_child:
                val_reg = ctx.lower_expr(value_child)
            else:
                val_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[str(i)],
                )
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, member_name, val_reg],
                node=enumerator,
            )

    ctx.emit(
        Opcode.STORE_VAR,
        operands=[enum_name, obj_reg],
        node=node,
    )


def lower_union_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower union_specifier like struct_specifier."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")

    if name_node is None and body_node is None:
        return

    union_name = ctx.node_text(name_node) if name_node else "__anon_union"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{union_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{union_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        lower_struct_body(ctx, body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=union_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[union_name, cls_reg])


def lower_typedef(ctx: TreeSitterEmitContext, node) -> None:
    """Lower type_definition as CONST type_name -> STORE_VAR alias."""
    named_children = [c for c in node.children if c.is_named]
    alias_node = next(
        (c for c in reversed(named_children) if c.type == "type_identifier"),
        None,
    )
    type_nodes = [
        c for c in named_children if c != alias_node and c.type != "type_identifier"
    ]
    type_name = ctx.node_text(type_nodes[0]) if type_nodes else "unknown_type"
    alias_name = ctx.node_text(alias_node) if alias_node else "unknown_alias"

    type_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=type_reg,
        operands=[type_name],
        node=node,
    )
    ctx.emit(
        Opcode.STORE_VAR,
        operands=[alias_name, type_reg],
        node=node,
    )


def lower_preproc_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `#define FUNC(args) body` as function stub."""
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    func_name = ctx.node_text(name_node) if name_node else "__macro"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    params_node = node.child_by_field_name("parameters")
    if params_node:
        lower_c_params(ctx, params_node)

    if value_node:
        val_reg = ctx.lower_expr(value_node)
        ctx.emit(Opcode.RETURN, operands=[val_reg])
    else:
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
