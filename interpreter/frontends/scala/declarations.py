"""Scala-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.scala.node_types import ScalaNodeType as NT
from interpreter.frontends.common.declarations import make_class_ref


def _extract_pattern_name(ctx: TreeSitterEmitContext, pattern_node) -> str:
    """Extract name from a pattern node (identifier, typed_pattern, etc.)."""
    if pattern_node is None:
        return "__unknown"
    if pattern_node.type == NT.IDENTIFIER:
        return ctx.node_text(pattern_node)
    # typed_pattern or other wrapper: find the identifier inside
    id_child = next(
        (c for c in pattern_node.children if c.type == NT.IDENTIFIER),
        None,
    )
    if id_child:
        return ctx.node_text(id_child)
    return ctx.node_text(pattern_node)


def _lower_scala_tuple_destructure(
    ctx: TreeSitterEmitContext, pattern_node, val_reg: str, parent_node
) -> None:
    """Lower `val (a, b) = expr` — emit LOAD_INDEX + STORE_VAR per element."""
    named_children = [
        c
        for c in pattern_node.children
        if c.type not in (NT.LPAREN, NT.RPAREN, NT.COMMA) and c.is_named
    ]
    for i, child in enumerate(named_children):
        var_name = _extract_pattern_name(ctx, child)
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
            operands=[var_name, elem_reg],
            node=parent_node,
        )


def _lower_val_or_var_def(ctx: TreeSitterEmitContext, node) -> None:
    """Shared logic for val_definition and var_definition, with tuple destructuring."""
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

    if pattern_node is not None and pattern_node.type == NT.TUPLE_PATTERN:
        _lower_scala_tuple_destructure(ctx, pattern_node, val_reg, node)
    else:
        var_name = _extract_pattern_name(ctx, pattern_node)
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[var_name, val_reg],
            node=node,
        )
        ctx.seed_var_type(var_name, type_hint)


def lower_val_def(ctx: TreeSitterEmitContext, node) -> None:
    _lower_val_or_var_def(ctx, node)


def lower_var_def(ctx: TreeSitterEmitContext, node) -> None:
    _lower_val_or_var_def(ctx, node)


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
    ctx.seed_param_type("this", class_name)
    ctx.emit(
        Opcode.STORE_VAR,
        operands=["this", param_reg],
    )
    ctx.seed_var_type("this", class_name)


def lower_scala_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        if child.type == NT.PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                raw_type = extract_type_from_field(ctx, child, "type")
                type_hint = normalize_type_hint(raw_type, ctx.type_map)
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=ctx.fresh_reg(),
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(f"%{ctx.reg_counter - 1}", type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit(
                    Opcode.STORE_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )
                ctx.seed_var_type(pname, type_hint)


def lower_function_def(
    ctx: TreeSitterEmitContext, node, inject_this: bool = False
) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if inject_this:
        _emit_this_param(ctx)

    if params_node:
        lower_scala_params(ctx, params_node)

    expr_returned = False
    if body_node:
        is_block = (
            body_node.type in ctx.constants.block_node_types
            or ctx.stmt_dispatch.get(body_node.type) is not None
        )
        if is_block:
            ctx.lower_block(body_node)
        else:
            val_reg = ctx.lower_expr(body_node)
            ctx.emit(Opcode.RETURN, operands=[val_reg])
            expr_returned = True

    if not expr_returned:
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


_CLASS_BODY_FUNC_TYPES = frozenset({NT.FUNCTION_DEFINITION})


def _lower_class_body_hoisted(
    ctx: TreeSitterEmitContext, node, inject_this: bool = False
) -> None:
    """Hoist all class-body children to top level.

    Emits function definitions first (so their refs are registered),
    then field initializers and other statements.
    """
    children = [
        c
        for c in node.children
        if c.is_named
        and c.type not in ctx.constants.comment_types
        and c.type not in ctx.constants.noise_types
    ]
    functions = [c for c in children if c.type in _CLASS_BODY_FUNC_TYPES]
    rest = [c for c in children if c.type not in _CLASS_BODY_FUNC_TYPES]
    for child in functions:
        lower_function_def(ctx, child, inject_this=inject_this)
    for child in rest:
        ctx.lower_stmt(child)


def _extract_scala_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class/trait names from a Scala class/trait/object definition."""
    extends_clause = next(
        (c for c in node.children if c.type == NT.EXTENDS_CLAUSE), None
    )
    if extends_clause is None:
        return []
    return [
        ctx.node_text(c)
        for c in extends_clause.children
        if c.type == NT.TYPE_IDENTIFIER
    ]


def lower_class_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"
    parents = _extract_scala_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[make_class_ref(class_name, class_label, parents)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])

    if body_node:
        saved_class = ctx._current_class_name
        ctx._current_class_name = class_name
        _lower_class_body_hoisted(ctx, body_node, inject_this=True)
        ctx._current_class_name = saved_class


def lower_object_def(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    obj_name = ctx.node_text(name_node) if name_node else "__anon_object"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{obj_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{obj_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=obj_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[obj_name, cls_reg])

    if body_node:
        _lower_class_body_hoisted(ctx, body_node)


def lower_trait_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower trait_definition like class_definition."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    trait_name = ctx.node_text(name_node) if name_node else "__anon_trait"
    parents = _extract_scala_parents(ctx, node)

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
        operands=[make_class_ref(trait_name, class_label, parents)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[trait_name, cls_reg])


def lower_function_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower abstract function declaration (no body) as function stub."""
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


def lower_function_def_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Statement-dispatch wrapper for function_definition."""
    lower_function_def(ctx, node)
