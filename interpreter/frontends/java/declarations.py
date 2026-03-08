"""Java-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.java.expressions import lower_java_params
from interpreter.frontends.type_extraction import (
    extract_normalized_type,
)
from interpreter.frontends.java.node_types import JavaNodeType
from interpreter.frontends.common.declarations import make_class_ref


def lower_local_var_decl(ctx: TreeSitterEmitContext, node) -> None:
    type_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)
    for child in node.children:
        if child.type == JavaNodeType.VARIABLE_DECLARATOR:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                val_reg = ctx.lower_expr(value_node)
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[ctx.node_text(name_node), val_reg],
                    node=node,
                )
                ctx.seed_var_type(ctx.node_text(name_node), type_hint)
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
                    node=node,
                )
                ctx.seed_var_type(ctx.node_text(name_node), type_hint)


def _emit_this_param(ctx: TreeSitterEmitContext) -> None:
    """Emit ``SYMBOLIC param:this`` + ``STORE_VAR this`` for instance methods."""
    param_reg = ctx.fresh_reg()
    class_name = ctx._current_class_name
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=param_reg,
        operands=[f"{constants.PARAM_PREFIX}this"],
    )
    ctx.seed_register_type(param_reg, class_name)
    ctx.seed_param_type(constants.PARAM_THIS, class_name)
    ctx.emit(
        Opcode.STORE_VAR,
        operands=[constants.PARAM_THIS, param_reg],
    )
    ctx.seed_var_type(constants.PARAM_THIS, class_name)


def _has_static_modifier(node) -> bool:
    """Return True if *node* has a ``static`` modifier."""
    return any(
        c.type == JavaNodeType.MODIFIERS
        and any(m.type == JavaNodeType.STATIC for m in c.children)
        for c in node.children
    )


def lower_method_decl(
    ctx: TreeSitterEmitContext, node, inject_this: bool = False
) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if inject_this:
        _emit_this_param(ctx)

    if params_node:
        lower_java_params(ctx, params_node)

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


def lower_method_decl_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Statement-dispatch wrapper: method_declaration as statement."""
    lower_method_decl(ctx, node)


_CLASS_BODY_METHOD_TYPES = frozenset(
    {JavaNodeType.METHOD_DECLARATION, JavaNodeType.CONSTRUCTOR_DECLARATION}
)
_CLASS_BODY_SKIP_TYPES = frozenset(
    {JavaNodeType.MODIFIERS, JavaNodeType.MARKER_ANNOTATION, JavaNodeType.ANNOTATION}
)


def _lower_class_body(ctx: TreeSitterEmitContext, node) -> list:
    """Collect class-body children for top-level hoisting. Methods first, then rest."""
    methods: list = []
    rest: list = []
    for child in node.children:
        if child.type in _CLASS_BODY_SKIP_TYPES or not child.is_named:
            continue
        elif child.type in _CLASS_BODY_METHOD_TYPES:
            methods.append(child)
        else:
            rest.append(child)
    return methods + rest


def _lower_deferred_class_child(ctx: TreeSitterEmitContext, child) -> None:
    """Lower a single deferred class-body child at top level."""
    if child.type == JavaNodeType.METHOD_DECLARATION:
        lower_method_decl(ctx, child, inject_this=not _has_static_modifier(child))
    elif child.type == JavaNodeType.CONSTRUCTOR_DECLARATION:
        _lower_constructor_decl(ctx, child)
    elif child.type == JavaNodeType.FIELD_DECLARATION:
        _lower_field_decl(ctx, child)
    elif child.type == JavaNodeType.STATIC_INITIALIZER:
        _lower_static_initializer(ctx, child)
    else:
        ctx.lower_stmt(child)


def _extract_java_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class and interface names from a Java class_declaration node."""
    parents: list[str] = []
    superclass_node = next(
        (c for c in node.children if c.type == JavaNodeType.SUPERCLASS), None
    )
    if superclass_node:
        parent_id = next(
            (
                c
                for c in superclass_node.children
                if c.type == JavaNodeType.TYPE_IDENTIFIER
            ),
            None,
        )
        if parent_id:
            parents.append(ctx.node_text(parent_id))
    # Extract interfaces from super_interfaces clause
    interfaces_node = next(
        (c for c in node.children if c.type == JavaNodeType.SUPER_INTERFACES), None
    )
    if interfaces_node:
        type_list = next(
            (c for c in interfaces_node.children if c.type == JavaNodeType.TYPE_LIST),
            None,
        )
        if type_list:
            interface_names = [
                ctx.node_text(c)
                for c in type_list.children
                if c.type == JavaNodeType.TYPE_IDENTIFIER
            ]
            parents.extend(interface_names)
    return parents


def _extract_java_interfaces(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract interface names from super_interfaces clause."""
    interfaces_node = next(
        (c for c in node.children if c.type == JavaNodeType.SUPER_INTERFACES), None
    )
    if not interfaces_node:
        return []
    type_list = next(
        (c for c in interfaces_node.children if c.type == JavaNodeType.TYPE_LIST),
        None,
    )
    if not type_list:
        return []
    return [
        ctx.node_text(c)
        for c in type_list.children
        if c.type == JavaNodeType.TYPE_IDENTIFIER
    ]


def lower_class_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"
    parents = _extract_java_parents(ctx, node)
    # Seed interface implementations
    for iface in _extract_java_interfaces(ctx, node):
        ctx.seed_interface_impl(class_name, iface)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    deferred = _lower_class_body(ctx, body_node) if body_node else []
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[make_class_ref(class_name, class_label, parents)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])

    saved_class = ctx._current_class_name
    ctx._current_class_name = class_name
    for child in deferred:
        _lower_deferred_class_child(ctx, child)
    ctx._current_class_name = saved_class


def lower_record_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower record_declaration like class_declaration."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    record_name = ctx.node_text(name_node) if name_node else "__anon_record"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{record_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{record_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    deferred = _lower_class_body(ctx, body_node) if body_node else []
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=record_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[record_name, cls_reg])

    saved_class = ctx._current_class_name
    ctx._current_class_name = record_name
    for child in deferred:
        _lower_deferred_class_child(ctx, child)
    ctx._current_class_name = saved_class


def _lower_constructor_decl(ctx: TreeSitterEmitContext, node) -> None:
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = "__init__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        lower_java_params(ctx, params_node)

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


def _lower_field_decl(ctx: TreeSitterEmitContext, node) -> None:
    type_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)
    for child in node.children:
        if child.type == JavaNodeType.VARIABLE_DECLARATOR:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                val_reg = ctx.lower_expr(value_node)
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[ctx.node_text(name_node), val_reg],
                    node=node,
                )
                ctx.seed_var_type(ctx.node_text(name_node), type_hint)


def _lower_static_initializer(ctx: TreeSitterEmitContext, node) -> None:
    """Lower static { ... } — find the block child and lower it."""
    block_node = next(
        (c for c in node.children if c.type == JavaNodeType.BLOCK),
        None,
    )
    if block_node:
        ctx.lower_block(block_node)


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
            member_name_node = child.child_by_field_name("name")
            member_name = (
                ctx.node_text(member_name_node)
                if member_name_node
                else ctx.node_text(child)[:40]
            )
            key_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
            val_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
            ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
    ctx.emit(Opcode.STORE_VAR, operands=[iface_name, obj_reg])


def lower_enum_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower enum_declaration as NEW_OBJECT with STORE_INDEX per member."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
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
            for i, child in enumerate(
                c for c in body_node.children if c.type == JavaNodeType.ENUM_CONSTANT
            ):
                member_name_node = child.child_by_field_name("name")
                member_name = (
                    ctx.node_text(member_name_node)
                    if member_name_node
                    else ctx.node_text(child)
                )
                key_reg = ctx.fresh_reg()
                ctx.emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
                val_reg = ctx.fresh_reg()
                ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
                ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
        ctx.emit(Opcode.STORE_VAR, operands=[enum_name, obj_reg])


def lower_annotation_type_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower @interface Name { ... } like interface declaration."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    if not name_node:
        return
    annot_name = ctx.node_text(name_node)
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[f"annotation:{annot_name}"],
        node=node,
    )
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    if body_node:
        for i, child in enumerate(c for c in body_node.children if c.is_named):
            member_name_node = child.child_by_field_name("name")
            member_name = (
                ctx.node_text(member_name_node)
                if member_name_node
                else ctx.node_text(child)[:40]
            )
            key_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
            val_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
            ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
    ctx.emit(Opcode.STORE_VAR, operands=[annot_name, obj_reg])
