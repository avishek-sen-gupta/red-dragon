"""Rust-specific declaration lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)

logger = logging.getLogger(__name__)


# ── Rust param handling ──────────────────────────────────────────────


def _extract_let_pattern_name(ctx: TreeSitterEmitContext, pattern_node) -> str:
    """Extract identifier from let pattern, handling `mut` wrapper."""
    if pattern_node is None:
        return "__unknown"
    if pattern_node.type == "identifier":
        return ctx.node_text(pattern_node)
    if pattern_node.type == "mutable_specifier":
        id_child = next(
            (c for c in pattern_node.children if c.type == "identifier"),
            None,
        )
        return ctx.node_text(id_child) if id_child else "__unknown"
    # mut pattern wrapping: children may contain mutable_specifier + identifier
    id_child = next(
        (c for c in pattern_node.children if c.type == "identifier"),
        None,
    )
    if id_child:
        return ctx.node_text(id_child)
    return ctx.node_text(pattern_node)


def _extract_rust_param_name(ctx: TreeSitterEmitContext, child) -> str | None:
    """Rust-specific param name extraction handling self_parameter and mut patterns."""
    if child.type == "identifier":
        return ctx.node_text(child)
    if child.type == "self_parameter":
        return "self"
    if child.type == "parameter":
        pattern_node = child.child_by_field_name("pattern")
        if pattern_node:
            return _extract_let_pattern_name(ctx, pattern_node)
    return None


def lower_rust_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower Rust function parameters."""
    for child in params_node.children:
        lower_rust_param(ctx, child)


def lower_rust_param(ctx: TreeSitterEmitContext, child) -> None:
    """Lower a single Rust function parameter to SYMBOLIC + STORE_VAR."""
    if child.type in ("(", ")", ",", ":", "->"):
        return
    pname = _extract_rust_param_name(ctx, child)
    if pname is None:
        return
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


# ── Function definition ─────────────────────────────────────────────


def lower_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Rust function_item with Rust-specific param handling."""
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label, type_hint=return_hint)

    if params_node:
        lower_rust_params(ctx, params_node)

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


# ── let declaration ──────────────────────────────────────────────────


def lower_let_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `let pattern = value;`."""
    pattern_node = node.child_by_field_name("pattern")
    value_node = node.child_by_field_name("value")
    raw_type = extract_type_from_field(ctx, node, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)
    if value_node:
        val_reg = ctx.lower_expr(value_node)
    else:
        val_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[ctx.constants.none_literal],
        )

    if pattern_node is not None and pattern_node.type == "tuple_pattern":
        _lower_tuple_destructure(ctx, pattern_node, val_reg, node)
    elif pattern_node is not None and pattern_node.type == "struct_pattern":
        _lower_struct_destructure(ctx, pattern_node, val_reg, node)
    else:
        var_name = _extract_let_pattern_name(ctx, pattern_node)
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[var_name, val_reg],
            node=node,
            type_hint=type_hint,
        )


def _lower_tuple_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower `let (a, b) = expr;` -- emit LOAD_INDEX + STORE_VAR per element."""
    named_children = [
        c for c in pattern_node.children if c.type not in ("(", ")", ",") and c.is_named
    ]
    for i, child in enumerate(named_children):
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        elem_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[val_reg, idx_reg],
            node=child,
        )
        var_name = _extract_let_pattern_name(ctx, child)
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[var_name, elem_reg],
            node=parent_node,
        )


def _lower_struct_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower `let Point { x, y } = expr;` -- emit LOAD_FIELD + STORE_VAR per field."""
    for child in pattern_node.children:
        if child.type == "field_pattern":
            id_node = next(
                (c for c in child.children if c.type == "shorthand_field_identifier"),
                None,
            )
            if id_node is None:
                id_node = next(
                    (c for c in child.children if c.type == "identifier"),
                    None,
                )
            if id_node is None:
                continue
            field_name = ctx.node_text(id_node)
            field_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.LOAD_FIELD,
                result_reg=field_reg,
                operands=[val_reg, field_name],
                node=child,
            )
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[field_name, field_reg],
                node=parent_node,
            )


# ── struct definition ────────────────────────────────────────────────


def lower_struct_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `struct Name { ... }`."""
    name_node = node.child_by_field_name("name")
    class_name = ctx.node_text(name_node) if name_node else "__anon_struct"
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
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


# ── impl block ───────────────────────────────────────────────────────


def lower_impl_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `impl Type { ... }`."""
    type_node = node.child_by_field_name("type")
    body_node = node.child_by_field_name("body")
    impl_name = ctx.node_text(type_node) if type_node else "__anon_impl"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{impl_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{impl_name}")

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
            constants.CLASS_REF_TEMPLATE.format(name=impl_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[impl_name, cls_reg])


# ── trait item ───────────────────────────────────────────────────────


def lower_trait_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `trait Name { ... }` like a class/impl block."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    trait_name = ctx.node_text(name_node) if name_node else "__anon_trait"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{trait_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{trait_name}")

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
            constants.CLASS_REF_TEMPLATE.format(name=trait_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[trait_name, cls_reg])


# ── enum item ────────────────────────────────────────────────────────


def lower_enum_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `enum Name { A, B(i32), ... }` as NEW_OBJECT + STORE_FIELD per variant."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    enum_name = ctx.node_text(name_node) if name_node else "__anon_enum"

    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=[f"enum:{enum_name}"],
        node=node,
    )

    if body_node:
        for child in body_node.children:
            if child.type in ("{", "}", ","):
                continue
            if not child.is_named:
                continue
            variant_name = ctx.node_text(child).split("(")[0].split("{")[0].strip()
            variant_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=variant_reg,
                operands=[variant_name],
            )
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, variant_name, variant_reg],
            )

    ctx.emit(Opcode.STORE_VAR, operands=[enum_name, obj_reg])


# ── const item ───────────────────────────────────────────────────────


def lower_const_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `const NAME: type = value;`."""
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    var_name = ctx.node_text(name_node) if name_node else "__const"
    raw_type = extract_type_from_field(ctx, node, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)

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


# ── static item ──────────────────────────────────────────────────────


def lower_static_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `static NAME: type = value;`."""
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    var_name = ctx.node_text(name_node) if name_node else "__static"
    raw_type = extract_type_from_field(ctx, node, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)

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


# ── type alias ───────────────────────────────────────────────────────


def lower_type_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `type Alias = OriginalType;`."""
    name_node = node.child_by_field_name("name")
    type_node = node.child_by_field_name("type")
    alias_name = ctx.node_text(name_node) if name_node else "__type_alias"
    type_text = ctx.node_text(type_node) if type_node else "()"

    val_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=val_reg,
        operands=[type_text],
        node=node,
    )
    ctx.emit(
        Opcode.STORE_VAR,
        operands=[alias_name, val_reg],
        node=node,
    )


# ── mod item ─────────────────────────────────────────────────────────


def lower_mod_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `mod name { ... }` by lowering the body block."""
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    logger.debug(
        "Lowering mod_item: %s",
        ctx.node_text(name_node) if name_node else "<anonymous>",
    )
    if body_node:
        ctx.lower_block(body_node)


# ── function signature item (trait method stub) ──────────────────────


def lower_function_signature(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `fn area(&self) -> f64;` as function stub (no body)."""
    name_node = node.child_by_field_name("name")
    func_name = ctx.node_text(name_node) if name_node else "__trait_fn"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    params_node = node.child_by_field_name("parameters")
    if params_node:
        lower_rust_params(ctx, params_node)

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
