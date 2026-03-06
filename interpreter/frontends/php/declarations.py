"""PHP-specific declaration lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.php.control_flow import lower_php_compound
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)


def lower_php_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower PHP function parameters."""
    for child in params_node.children:
        if child.type in ("(", ")", ","):
            continue
        if child.type == "simple_parameter":
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                raw_type = extract_type_from_field(ctx, child, "type")
                type_hint = normalize_type_hint(raw_type, ctx.type_map)
                reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=reg,
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )
                ctx.seed_var_type(pname, type_hint)
        elif child.type == "variadic_parameter":
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                raw_type = extract_type_from_field(ctx, child, "type")
                type_hint = normalize_type_hint(raw_type, ctx.type_map)
                reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=reg,
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )
                ctx.seed_var_type(pname, type_hint)
        elif child.type == "variable_name":
            pname = ctx.node_text(child)
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


def _emit_this_param(ctx: TreeSitterEmitContext) -> None:
    """Emit ``SYMBOLIC param:$this`` + ``STORE_VAR $this`` for instance methods."""
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=ctx.fresh_reg(),
        operands=[f"{constants.PARAM_PREFIX}$this"],
    )
    ctx.emit(
        Opcode.STORE_VAR,
        operands=["$this", f"%{ctx.reg_counter - 1}"],
    )


def _has_static_modifier(node) -> bool:
    """Return True if *node* has a ``static_modifier`` child."""
    return any(c.type == "static_modifier" for c in node.children)


def lower_php_func_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function definition."""
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if params_node:
        lower_php_params(ctx, params_node)

    if body_node:
        lower_php_compound(ctx, body_node)

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


def lower_php_method_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower method declaration inside a class."""
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if not _has_static_modifier(node):
        _emit_this_param(ctx)

    if params_node:
        lower_php_params(ctx, params_node)

    if body_node:
        lower_php_compound(ctx, body_node)

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


def _lower_php_class_body(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declaration_list body of a PHP class."""
    for child in node.children:
        if child.type == "method_declaration":
            lower_php_method_decl(ctx, child)
        elif child.type == "property_declaration":
            lower_php_property_declaration(ctx, child)
        elif child.is_named and child.type not in (
            "visibility_modifier",
            "static_modifier",
            "abstract_modifier",
            "final_modifier",
            "{",
            "}",
        ):
            ctx.lower_stmt(child)


def lower_php_class(ctx: TreeSitterEmitContext, node) -> None:
    """Lower class declaration."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    if body_node:
        _lower_php_class_body(ctx, body_node)

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


def lower_php_interface(ctx: TreeSitterEmitContext, node) -> None:
    """Lower interface_declaration like a class: BRANCH, LABEL, body, end."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    iface_name = ctx.node_text(name_node) if name_node else "__anon_interface"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{iface_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{iface_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    if body_node:
        _lower_php_class_body(ctx, body_node)

    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=iface_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[iface_name, cls_reg])


def lower_php_trait(ctx: TreeSitterEmitContext, node) -> None:
    """Lower trait_declaration like a class: BRANCH, LABEL, body, end."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    trait_name = ctx.node_text(name_node) if name_node else "__anon_trait"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{trait_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{trait_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    if body_node:
        _lower_php_class_body(ctx, body_node)

    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=trait_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[trait_name, cls_reg])


def lower_php_function_static(ctx: TreeSitterEmitContext, node) -> None:
    """Lower static $x = val; declarations inside functions."""
    for child in node.children:
        if child.type == "static_variable_declaration":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                val_reg = ctx.lower_expr(value_node)
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[ctx.node_text(name_node), val_reg],
                    node=child,
                )
            elif name_node:
                val_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[ctx.constants.none_literal],
                )
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[ctx.node_text(name_node), val_reg],
                    node=child,
                )


def lower_php_enum(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum_declaration like a class: BRANCH, LABEL, body, end."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    enum_name = ctx.node_text(name_node) if name_node else "__anon_enum"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{enum_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{enum_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    if body_node:
        _lower_php_class_body(ctx, body_node)

    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=enum_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[enum_name, cls_reg])


def lower_php_property_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower property declarations inside classes, e.g. public $x = 10;"""
    for child in node.children:
        if child.type == "property_element":
            name_node = next(
                (c for c in child.children if c.type == "variable_name"), None
            )
            value_node = next(
                (c for c in child.children if c.is_named and c.type != "variable_name"),
                None,
            )
            if name_node and value_node:
                val_reg = ctx.lower_expr(value_node)
                ctx.emit(
                    Opcode.STORE_FIELD,
                    operands=["self", ctx.node_text(name_node), val_reg],
                    node=node,
                )
            elif name_node:
                val_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[ctx.constants.none_literal],
                )
                ctx.emit(
                    Opcode.STORE_FIELD,
                    operands=["self", ctx.node_text(name_node), val_reg],
                    node=node,
                )


def lower_php_use_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``use SomeTrait;`` inside classes -- no-op / SYMBOLIC."""
    named = [c for c in node.children if c.is_named]
    trait_names = [ctx.node_text(c) for c in named]
    for trait_name in trait_names:
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=ctx.fresh_reg(),
            operands=[f"use_trait:{trait_name}"],
            node=node,
        )


def lower_php_namespace_use_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``use Some\\Namespace;`` -- no-op."""
    pass


def lower_php_enum_case(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum case inside an enum_declaration as STORE_FIELD."""
    name_node = node.child_by_field_name("name")
    value_node = next(
        (c for c in node.children if c.is_named and c.type not in ("name",)),
        None,
    )
    if name_node:
        case_name = ctx.node_text(name_node)
        if value_node:
            val_reg = ctx.lower_expr(value_node)
        else:
            val_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[case_name],
            )
        ctx.emit(
            Opcode.STORE_FIELD,
            operands=["self", case_name, val_reg],
            node=node,
        )


def lower_php_global_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower ``global $config;`` -- STORE_VAR for each variable."""
    for child in node.children:
        if child.type == "variable_name":
            var_name = ctx.node_text(child)
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.LOAD_VAR,
                result_reg=reg,
                operands=[var_name],
                node=child,
            )
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[var_name, reg],
                node=node,
            )
