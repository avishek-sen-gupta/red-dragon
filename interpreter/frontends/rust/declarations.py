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
from interpreter.frontends.rust.node_types import RustNodeType
from interpreter.register import Register

logger = logging.getLogger(__name__)


# ── Rust param handling ──────────────────────────────────────────────


def _extract_let_pattern_name(ctx: TreeSitterEmitContext, pattern_node) -> str:
    """Extract identifier from let pattern, handling `mut` wrapper."""
    if pattern_node is None:
        return "__unknown"
    if pattern_node.type == RustNodeType.IDENTIFIER:
        return ctx.node_text(pattern_node)
    if pattern_node.type == RustNodeType.MUTABLE_SPECIFIER:
        id_child = next(
            (c for c in pattern_node.children if c.type == RustNodeType.IDENTIFIER),
            None,
        )
        return ctx.node_text(id_child) if id_child else "__unknown"
    # mut pattern wrapping: children may contain mutable_specifier + identifier
    id_child = next(
        (c for c in pattern_node.children if c.type == RustNodeType.IDENTIFIER),
        None,
    )
    if id_child:
        return ctx.node_text(id_child)
    return ctx.node_text(pattern_node)


def _extract_rust_param_name(ctx: TreeSitterEmitContext, child) -> str | None:
    """Rust-specific param name extraction handling self_parameter and mut patterns."""
    if child.type == RustNodeType.IDENTIFIER:
        return ctx.node_text(child)
    if child.type == RustNodeType.SELF_PARAMETER:
        return "self"
    if child.type == RustNodeType.PARAMETER:
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
    if child.type in (
        RustNodeType.OPEN_PAREN,
        RustNodeType.CLOSE_PAREN,
        RustNodeType.COMMA,
        RustNodeType.COLON,
        RustNodeType.ARROW,
    ):
        return
    pname = _extract_rust_param_name(ctx, child)
    if pname is None:
        return
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
        Opcode.DECL_VAR,
        operands=[pname, f"%{ctx.reg_counter - 1}"],
    )
    ctx.seed_var_type(pname, type_hint)


# ── Function definition ─────────────────────────────────────────────


def _lower_rust_body_with_implicit_return(
    ctx: TreeSitterEmitContext, body_node
) -> Register:
    """Lower a Rust block body, returning the last bare-expression register.

    Rust uses expression-oriented semantics: a block ending with a bare
    expression (no trailing ``;``) returns that expression's value.  A block
    ending with a statement (``expression_statement``, which always carries a
    ``;`` in tree-sitter) is lowered as a statement and an empty string is
    returned — the caller should emit ``CONST () + RETURN`` as fallback.

    This mirrors Ruby's ``_lower_body_with_implicit_return``.
    """
    children = [
        c
        for c in body_node.children
        if c.is_named
        and c.type
        not in (
            RustNodeType.OPEN_BRACE,
            RustNodeType.CLOSE_BRACE,
            RustNodeType.SEMICOLON,
        )
        and c.type not in ctx.constants.comment_types
        and c.type not in ctx.constants.noise_types
    ]
    if not children:
        return ""
    *init, last = children
    for child in init:
        ctx.lower_stmt(child)
    # expression_statement (ends with ;) is a statement, NOT an implicit return
    is_stmt = (
        ctx.stmt_dispatch.get(last.type) is not None
        or last.type in ctx.constants.block_node_types
        or last.type == RustNodeType.EXPRESSION_STATEMENT
    )
    if is_stmt:
        ctx.lower_stmt(last)
        return ""
    return ctx.lower_expr(last)


def lower_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Rust function_item with Rust-specific param handling.

    Uses ``_lower_rust_body_with_implicit_return`` so that:
    - a bare expression at the end of the block becomes the implicit return;
    - an explicit ``return expr;`` (which is an ``expression_statement``) is
      lowered as a statement and the existing ``RETURN`` it emits is used.
    """
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if params_node:
        lower_rust_params(ctx, params_node)

    if body_node:
        expr_reg = _lower_rust_body_with_implicit_return(ctx, body_node)
        if expr_reg:
            ctx.emit(Opcode.RETURN, operands=[expr_reg])
        else:
            none_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=none_reg,
                operands=[ctx.constants.default_return_value],
            )
            ctx.emit(Opcode.RETURN, operands=[none_reg])
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
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


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

    if pattern_node is not None and pattern_node.type == RustNodeType.TUPLE_PATTERN:
        _lower_tuple_destructure(ctx, pattern_node, val_reg, node)
    elif pattern_node is not None and pattern_node.type == RustNodeType.STRUCT_PATTERN:
        _lower_struct_destructure(ctx, pattern_node, val_reg, node)
    else:
        raw_name = _extract_let_pattern_name(ctx, pattern_node)
        var_name = ctx.declare_block_var(raw_name)
        ctx.emit(
            Opcode.DECL_VAR,
            operands=[var_name, val_reg],
            node=node,
        )
        ctx.seed_var_type(var_name, type_hint)


def _lower_tuple_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower `let (a, b) = expr;` -- emit LOAD_INDEX + STORE_VAR per element."""
    named_children = [
        c
        for c in pattern_node.children
        if c.type
        not in (RustNodeType.OPEN_PAREN, RustNodeType.CLOSE_PAREN, RustNodeType.COMMA)
        and c.is_named
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
            Opcode.DECL_VAR,
            operands=[var_name, elem_reg],
            node=parent_node,
        )


def _lower_struct_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower `let Point { x, y } = expr;` -- emit LOAD_FIELD + STORE_VAR per field."""
    for child in pattern_node.children:
        if child.type == RustNodeType.FIELD_PATTERN:
            id_node = next(
                (
                    c
                    for c in child.children
                    if c.type == RustNodeType.SHORTHAND_FIELD_IDENTIFIER
                ),
                None,
            )
            if id_node is None:
                id_node = next(
                    (c for c in child.children if c.type == RustNodeType.IDENTIFIER),
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
                Opcode.DECL_VAR,
                operands=[field_name, field_reg],
                node=parent_node,
            )


# ── struct definition ────────────────────────────────────────────────


def lower_struct_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `struct Name { ... }`."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    class_name = ctx.node_text(name_node) if name_node else "__anon_struct"
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, [], result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])


# ── impl block ───────────────────────────────────────────────────────


def lower_impl_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `impl Type { ... }`."""
    type_node = node.child_by_field_name("type")
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    impl_name = ctx.node_text(type_node) if type_node else "__anon_impl"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{impl_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{impl_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(impl_name, class_label, [], result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[impl_name, cls_reg])


# ── trait item ───────────────────────────────────────────────────────


def lower_trait_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `trait Name { ... }` like a class/impl block."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    trait_name = ctx.node_text(name_node) if name_node else "__anon_trait"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{trait_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{trait_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(trait_name, class_label, [], result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[trait_name, cls_reg])


# ── enum item ────────────────────────────────────────────────────────


def lower_enum_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `enum Name { A, B(i32), ... }` as NEW_OBJECT + STORE_FIELD per variant."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
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
            if child.type in (
                RustNodeType.OPEN_BRACE,
                RustNodeType.CLOSE_BRACE,
                RustNodeType.COMMA,
            ):
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

    ctx.emit(Opcode.DECL_VAR, operands=[enum_name, obj_reg])


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
        Opcode.DECL_VAR,
        operands=[var_name, val_reg],
        node=node,
    )
    ctx.seed_var_type(var_name, type_hint)


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
        Opcode.DECL_VAR,
        operands=[var_name, val_reg],
        node=node,
    )
    ctx.seed_var_type(var_name, type_hint)


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
        Opcode.DECL_VAR,
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


# ── foreign mod item (extern block) ──────────────────────────────────


def lower_foreign_mod_item(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `extern "C" { fn foo(); ... }` by lowering body declarations."""
    body_node = node.child_by_field_name("body")
    if body_node:
        for child in body_node.children:
            if child.is_named and child.type != RustNodeType.STRING_LITERAL:
                ctx.lower_stmt(child)


# ── function signature item (trait method stub) ──────────────────────


def lower_function_signature(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `fn area(&self) -> f64;` as function stub (no body)."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    func_name = ctx.node_text(name_node) if name_node else "__trait_fn"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
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
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


# ── Rust prelude (Box, Option) ─────────────────────────────────────────


def emit_prelude(ctx: TreeSitterEmitContext) -> None:
    """Emit Box and Option class definitions as IR prelude."""
    _emit_box_class(ctx)
    _emit_option_class(ctx)
    _register_prelude_in_symbol_table(ctx)


def _register_prelude_in_symbol_table(ctx: TreeSitterEmitContext) -> None:
    """Register Option and Box in symbol table with match_args for pattern matching."""
    from interpreter.frontends.symbol_table import ClassInfo, FieldInfo

    ctx.symbol_table.classes["Option"] = ClassInfo(
        name="Option",
        fields={
            "value": FieldInfo(name="value", type_hint="Any", has_initializer=True)
        },
        methods={},
        constants={},
        parents=(),
        match_args=("value",),
    )
    ctx.symbol_table.classes["Box"] = ClassInfo(
        name="Box",
        fields={
            constants.BOXED_FIELD: FieldInfo(
                name=constants.BOXED_FIELD, type_hint="Any", has_initializer=True
            )
        },
        methods={},
        constants={},
        parents=(),
        match_args=(constants.BOXED_FIELD,),
    )


def _emit_method_params(ctx: TreeSitterEmitContext, param_names: list[str]) -> None:
    """Emit SYMBOLIC param: + STORE_VAR for each parameter."""
    for pname in param_names:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"{constants.PARAM_PREFIX}{pname}"],
        )
        ctx.emit(Opcode.DECL_VAR, operands=[pname, reg])


def _emit_prelude_func_ref(
    ctx: TreeSitterEmitContext, func_name: str, func_label: str
) -> None:
    """Emit CONST <function:name@label> + STORE_VAR."""
    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def _emit_box_class(ctx: TreeSitterEmitContext) -> None:
    """Emit Box class: __init__ + __method_missing__ for auto-deref delegation."""
    class_name = "Box"
    class_label = ctx.fresh_label(f"{constants.PRELUDE_CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(
        f"{constants.PRELUDE_END_CLASS_LABEL_PREFIX}{class_name}"
    )
    init_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{class_name}___init__")
    init_end = ctx.fresh_label(f"end_{class_name}___init__")
    mm_label = ctx.fresh_label(
        f"{constants.FUNC_LABEL_PREFIX}{class_name}___{constants.METHOD_MISSING}"
    )
    mm_end = ctx.fresh_label(f"end_{class_name}___{constants.METHOD_MISSING}")

    # Class body — branch past it
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=class_label)

    # __init__(self, value) body
    ctx.emit(Opcode.BRANCH, label=init_end)
    ctx.emit(Opcode.LABEL, label=init_label)
    _emit_method_params(ctx, [constants.PARAM_SELF, "value"])
    self_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=self_reg, operands=[constants.PARAM_SELF])
    val_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=val_reg, operands=["value"])
    ctx.emit(Opcode.STORE_FIELD, operands=[self_reg, constants.BOXED_FIELD, val_reg])
    ctx.emit(Opcode.RETURN, operands=[self_reg])
    ctx.emit(Opcode.LABEL, label=init_end)

    # __method_missing__(self, name) body
    ctx.emit(Opcode.BRANCH, label=mm_end)
    ctx.emit(Opcode.LABEL, label=mm_label)
    _emit_method_params(ctx, [constants.PARAM_SELF, "name"])
    mm_self = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=mm_self, operands=[constants.PARAM_SELF])
    mm_inner = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=mm_inner,
        operands=[mm_self, constants.BOXED_FIELD],
    )
    mm_name = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=mm_name, operands=["name"])
    mm_result = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD_INDIRECT,
        result_reg=mm_result,
        operands=[mm_inner, mm_name],
    )
    ctx.emit(Opcode.RETURN, operands=[mm_result])
    ctx.emit(Opcode.LABEL, label=mm_end)

    # Register methods — CONST func_ref INSIDE class body
    _emit_prelude_func_ref(ctx, "__init__", init_label)
    _emit_prelude_func_ref(ctx, constants.METHOD_MISSING, mm_label)

    ctx.emit(Opcode.LABEL, label=end_label)

    # Store class ref (OUTSIDE class body, after end_label)
    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, [], result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])


def _emit_option_class(ctx: TreeSitterEmitContext) -> None:
    """Emit Option class: __init__, unwrap, as_ref methods."""
    class_name = "Option"
    class_label = ctx.fresh_label(f"{constants.PRELUDE_CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(
        f"{constants.PRELUDE_END_CLASS_LABEL_PREFIX}{class_name}"
    )
    init_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{class_name}___init__")
    init_end = ctx.fresh_label(f"end_{class_name}___init__")
    unwrap_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{class_name}__unwrap")
    unwrap_end = ctx.fresh_label(f"end_{class_name}__unwrap")
    as_ref_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{class_name}__as_ref")
    as_ref_end = ctx.fresh_label(f"end_{class_name}__as_ref")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=class_label)

    # __init__(self, value) body
    ctx.emit(Opcode.BRANCH, label=init_end)
    ctx.emit(Opcode.LABEL, label=init_label)
    _emit_method_params(ctx, [constants.PARAM_SELF, "value"])
    self_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=self_reg, operands=[constants.PARAM_SELF])
    val_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=val_reg, operands=["value"])
    ctx.emit(Opcode.STORE_FIELD, operands=[self_reg, "value", val_reg])
    ctx.emit(Opcode.RETURN, operands=[self_reg])
    ctx.emit(Opcode.LABEL, label=init_end)

    # unwrap(self) body
    ctx.emit(Opcode.BRANCH, label=unwrap_end)
    ctx.emit(Opcode.LABEL, label=unwrap_label)
    _emit_method_params(ctx, [constants.PARAM_SELF])
    self_reg2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=self_reg2, operands=[constants.PARAM_SELF])
    val_reg2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_FIELD, result_reg=val_reg2, operands=[self_reg2, "value"])
    ctx.emit(Opcode.RETURN, operands=[val_reg2])
    ctx.emit(Opcode.LABEL, label=unwrap_end)

    # as_ref(self) body
    ctx.emit(Opcode.BRANCH, label=as_ref_end)
    ctx.emit(Opcode.LABEL, label=as_ref_label)
    _emit_method_params(ctx, [constants.PARAM_SELF])
    self_reg3 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=self_reg3, operands=[constants.PARAM_SELF])
    ctx.emit(Opcode.RETURN, operands=[self_reg3])
    ctx.emit(Opcode.LABEL, label=as_ref_end)

    # Register all 3 methods — CONST func_ref INSIDE class body
    _emit_prelude_func_ref(ctx, "__init__", init_label)
    _emit_prelude_func_ref(ctx, "unwrap", unwrap_label)
    _emit_prelude_func_ref(ctx, "as_ref", as_ref_label)

    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, [], result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])


# ---------------------------------------------------------------------------
# Symbol extraction (Phase 2)
# ---------------------------------------------------------------------------


def _extract_rust_struct_fields(field_declaration_list) -> "dict[str, FieldInfo]":
    """Extract fields from a Rust field_declaration_list node."""
    from interpreter.frontends.symbol_table import FieldInfo

    fields: dict[str, FieldInfo] = {}
    for child in field_declaration_list.children:
        if child.type != "field_declaration":
            continue
        name_node = child.child_by_field_name("name")
        type_node = child.child_by_field_name("type")
        if name_node is not None:
            fname = name_node.text.decode()
            type_hint = type_node.text.decode() if type_node is not None else ""
            fields[fname] = FieldInfo(
                name=fname, type_hint=type_hint, has_initializer=False
            )
    return fields


def _extract_rust_struct(node) -> "tuple[str, ClassInfo] | None":
    """Extract a ClassInfo from a Rust struct_item node."""
    from interpreter.frontends.symbol_table import ClassInfo, FieldInfo

    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    struct_name = name_node.text.decode()

    field_list = next(
        (c for c in node.children if c.type == "field_declaration_list"),
        None,
    )
    fields: dict[str, FieldInfo] = (
        _extract_rust_struct_fields(field_list) if field_list is not None else {}
    )
    return struct_name, ClassInfo(
        name=struct_name, fields=fields, methods={}, constants={}, parents=()
    )


def _collect_rust_structs_and_impls(
    node,
    classes: "dict[str, ClassInfo]",
    functions: "dict[str, FunctionInfo]",
) -> None:
    """Walk AST to collect struct definitions and impl blocks (methods)."""
    from interpreter.frontends.symbol_table import ClassInfo, FunctionInfo

    if node.type == RustNodeType.STRUCT_ITEM:
        result = _extract_rust_struct(node)
        if result is not None:
            sname, sinfo = result
            classes[sname] = sinfo
    elif node.type == RustNodeType.IMPL_ITEM:
        type_node = node.child_by_field_name("type")
        if type_node is not None:
            impl_type = type_node.text.decode().split("<")[0]
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    if child.type == RustNodeType.FUNCTION_ITEM:
                        fname_node = child.child_by_field_name("name")
                        params_node = child.child_by_field_name("parameters")
                        if fname_node is not None:
                            mname = fname_node.text.decode()
                            params = (
                                tuple(
                                    p.child_by_field_name("pattern").text.decode()
                                    for p in params_node.children
                                    if p.type == RustNodeType.PARAMETER
                                    and p.child_by_field_name("pattern") is not None
                                )
                                if params_node is not None
                                else ()
                            )
                            minfo = FunctionInfo(
                                name=mname, params=params, return_type=""
                            )
                            if impl_type in classes:
                                classes[impl_type].methods[mname] = minfo
                            else:
                                functions[mname] = minfo
    elif node.type == RustNodeType.FUNCTION_ITEM and (
        node.parent is None or node.parent.type != "declaration_list"
    ):
        # Only top-level functions — impl methods are handled in the impl_item branch
        fname_node = node.child_by_field_name("name")
        if fname_node is not None:
            fname = fname_node.text.decode()
            params_node = node.child_by_field_name("parameters")
            params = (
                tuple(
                    p.child_by_field_name("pattern").text.decode()
                    for p in params_node.children
                    if p.type == RustNodeType.PARAMETER
                    and p.child_by_field_name("pattern") is not None
                )
                if params_node is not None
                else ()
            )
            functions[fname] = FunctionInfo(name=fname, params=params, return_type="")
    for child in node.children:
        _collect_rust_structs_and_impls(child, classes, functions)


def extract_rust_symbols(root) -> "SymbolTable":
    """Walk the Rust AST and return a SymbolTable of all struct definitions."""
    from interpreter.frontends.symbol_table import ClassInfo, FunctionInfo, SymbolTable

    classes: dict[str, ClassInfo] = {}
    functions: dict[str, FunctionInfo] = {}
    _collect_rust_structs_and_impls(root, classes, functions)
    return SymbolTable(classes=classes, functions=functions)
