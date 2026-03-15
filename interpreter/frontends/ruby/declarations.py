"""Ruby-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.ruby.expressions import lower_ruby_params
from interpreter.frontends.ruby.node_types import RubyNodeType
from interpreter.frontends.common.declarations import make_class_ref


def _lower_body_with_implicit_return(ctx: TreeSitterEmitContext, body_node) -> str:
    """Lower a Ruby method body, returning the last expression's register if implicit return applies.

    If the last named child is an expression (not a statement), it is lowered
    via ``lower_expr`` and its register is returned. Otherwise all children are
    lowered as statements and an empty string is returned.
    """
    children = [
        c
        for c in body_node.children
        if c.is_named
        and c.type not in ctx.constants.comment_types
        and c.type not in ctx.constants.noise_types
    ]
    if not children:
        return ""
    *init, last = children
    for child in init:
        ctx.lower_stmt(child)
    is_stmt = (
        ctx.stmt_dispatch.get(last.type) is not None
        or last.type in ctx.constants.block_node_types
    )
    if is_stmt:
        ctx.lower_stmt(last)
        return ""
    return ctx.lower_expr(last)


def _emit_self_param(ctx: TreeSitterEmitContext) -> None:
    """Emit ``SYMBOLIC param:self`` + ``STORE_VAR self`` for instance methods."""
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=ctx.fresh_reg(),
        operands=[f"{constants.PARAM_PREFIX}self"],
    )
    ctx.emit(
        Opcode.DECL_VAR,
        operands=[constants.PARAM_SELF, f"%{ctx.reg_counter - 1}"],
    )


def lower_ruby_method(
    ctx: TreeSitterEmitContext, node, inject_self: bool = False
) -> None:
    """Lower Ruby method definition."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    raw_name = ctx.node_text(name_node) if name_node else "__anon"
    func_name = "__init__" if (inject_self and raw_name == "initialize") else raw_name
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    if inject_self:
        _emit_self_param(ctx)

    if params_node:
        lower_ruby_params(ctx, params_node)

    expr_reg = ""
    if body_node:
        expr_reg = _lower_body_with_implicit_return(ctx, body_node)

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
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_ruby_method_stmt(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Ruby method as a statement (no inject_self)."""
    lower_ruby_method(ctx, node, inject_self=False)


def _extract_ruby_parents(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract parent class name from a Ruby class definition (single inheritance)."""
    superclass_node = next(
        (c for c in node.children if c.type == RubyNodeType.SUPERCLASS), None
    )
    if superclass_node is None:
        return []
    parent_id = next(
        (c for c in superclass_node.children if c.type == RubyNodeType.CONSTANT),
        None,
    )
    return [ctx.node_text(parent_id)] if parent_id else []


def lower_ruby_class(ctx: TreeSitterEmitContext, node) -> None:
    """Lower Ruby class definition with method body handling."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node) if name_node else "__anon_class"
    parents = _extract_ruby_parents(ctx, node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
    if body_node:
        for child in body_node.children:
            if child.type == RubyNodeType.METHOD:
                lower_ruby_method(ctx, child, inject_self=True)
            elif child.is_named:
                ctx.lower_stmt(child)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[make_class_ref(class_name, class_label, parents)],
    )
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])


def lower_ruby_singleton_class(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `class << obj ... end` — lower the body."""
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    value_node = node.child_by_field_name("value")

    class_label = ctx.fresh_label("singleton_class")
    end_label = ctx.fresh_label("singleton_class_end")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    if value_node:
        ctx.lower_expr(value_node)

    if body_node:
        ctx.lower_block(body_node)

    ctx.emit(Opcode.LABEL, label=end_label)


def lower_ruby_singleton_method(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `def self.method_name(...) ... end` — like a regular method."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    object_node = node.child_by_field_name(ctx.constants.attr_object_field)

    object_name = ctx.node_text(object_node) if object_node else "self"
    method_name = ctx.node_text(name_node) if name_node else "__anon"
    func_name = f"{object_name}.{method_name}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        lower_ruby_params(ctx, params_node)

    expr_reg = ""
    if body_node:
        expr_reg = _lower_body_with_implicit_return(ctx, body_node)

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
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_ruby_module(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `module Name; ...; end` like a class."""
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    module_name = ctx.node_text(name_node) if name_node else "__anon_module"

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{module_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{module_name}")

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
            constants.CLASS_REF_TEMPLATE.format(name=module_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.DECL_VAR, operands=[module_name, cls_reg])
