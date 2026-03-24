"""Common declaration lowerers — pure functions taking (ctx, node).

Extracted from BaseFrontend: function_def, params, class_def, var_declaration.
"""

from __future__ import annotations

from typing import Callable

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.common.node_types import CommonNodeType

from interpreter import constants
from interpreter.instructions import (
    Branch,
    Const,
    DeclVar,
    Label_,
    LoadVar,
    Return_,
    StoreField,
    Symbolic,
)
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)


def extract_param_name(ctx: TreeSitterEmitContext, child) -> str | None:
    """Extract parameter name from a parameter node."""
    if child.type == CommonNodeType.IDENTIFIER:
        return ctx.node_text(child)
    # Try common field names
    for field in ("name", "pattern"):
        name_node = child.child_by_field_name(field)
        if name_node:
            return ctx.node_text(name_node)
    # Try first identifier child
    id_node = next(
        (sub for sub in child.children if sub.type == CommonNodeType.IDENTIFIER),
        None,
    )
    if id_node:
        return ctx.node_text(id_node)
    return None


def lower_param(ctx: TreeSitterEmitContext, child) -> None:
    """Lower a single function parameter to SYMBOLIC + STORE_VAR."""
    if child.type in (
        CommonNodeType.OPEN_PAREN,
        CommonNodeType.CLOSE_PAREN,
        CommonNodeType.COMMA,
        CommonNodeType.COLON,
        CommonNodeType.ARROW,
    ):
        return
    pname = extract_param_name(ctx, child)
    if pname is None:
        return
    raw_type = extract_type_from_field(ctx, child, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)
    param_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(
            result_reg=param_reg,
            hint=f"{constants.PARAM_PREFIX}{pname}",
        ),
        node=child,
    )
    ctx.seed_register_type(param_reg, type_hint)
    ctx.seed_param_type(pname, type_hint)
    ctx.emit_inst(
        DeclVar(
            name=pname,
            value_reg=f"%{ctx.reg_counter - 1}",
        ),
        node=child,
    )
    ctx.seed_var_type(pname, type_hint)


def lower_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower function parameters. Override for language-specific param shapes."""
    for child in params_node.children:
        lower_param(ctx, child)


def lower_function_def(
    ctx: TreeSitterEmitContext,
    node,
    params_lowerer: Callable = lower_params,
) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node)
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "return_type")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))
    ctx.seed_func_return_type(func_label, return_hint)

    if params_node:
        params_lowerer(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    # Implicit return at end of function
    none_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Const(
            result_reg=none_reg,
            value=ctx.constants.default_return_value,
        ),
        node=node,
    )
    ctx.emit_inst(Return_(value_reg=str(none_reg)), node=node)

    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg, node=node)
    ctx.emit_inst(DeclVar(name=func_name, value_reg=str(func_reg)), node=node)


FieldInit = tuple  # (field_name: str, value_node)


def emit_field_initializers(
    ctx: TreeSitterEmitContext,
    field_inits: list[FieldInit],
    this_var: str = "this",
) -> None:
    """Emit STORE_FIELD this <name> <value> for each collected field initializer.

    Call at the start of a constructor body (after this is available via var_writes)
    to properly initialize instance fields on the heap object.  This mirrors how
    real compilers (javac, Roslyn, kotlinc) prepend field initializers to every
    constructor body.

    *this_var* defaults to ``"this"`` but can be overridden (e.g. ``"$this"``
    for PHP).
    """
    for field_name, value_node in field_inits:
        val_reg = ctx.lower_expr(value_node)
        this_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=this_reg, name=this_var))
        ctx.emit_inst(
            StoreField(
                obj_reg=str(this_reg),
                field_name=field_name,
                value_reg=str(val_reg),
            ),
        )


def emit_synthetic_init(
    ctx: TreeSitterEmitContext,
    field_inits: list[FieldInit],
    constructor_name: str = "__init__",
    this_var: str = "this",
) -> None:
    """Generate a synthetic constructor that initializes fields.

    Used when a class has field initializers but no explicit constructor.
    The generated constructor emits STORE_FIELD for each field initializer,
    then returns None.  The ``this`` variable is set by the VM's
    constructor call mechanism via var_writes.

    *constructor_name* defaults to ``__init__`` but can be overridden
    (e.g. ``__construct`` for PHP).  *this_var* defaults to ``"this"``
    but can be overridden (e.g. ``"$this"`` for PHP).
    """
    func_name = constructor_name
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    emit_field_initializers(ctx, field_inits, this_var=this_var)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Const(
            result_reg=none_reg,
            value=ctx.constants.default_return_value,
        ),
    )
    ctx.emit_inst(Return_(value_reg=str(none_reg)))
    ctx.emit_inst(Label_(label=end_label))

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit_inst(DeclVar(name=func_name, value_reg=str(func_reg)))


def lower_class_def(ctx: TreeSitterEmitContext, node, parents: list[str] = []) -> None:
    name_node = node.child_by_field_name(ctx.constants.class_name_field)
    body_node = node.child_by_field_name(ctx.constants.class_body_field)
    class_name = ctx.node_text(name_node)

    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=class_label))
    if body_node:
        ctx.lower_block(body_node)
    ctx.emit_inst(Label_(label=end_label))

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
    ctx.emit_inst(DeclVar(name=class_name, value_reg=str(cls_reg)), node=node)


def lower_var_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a variable declaration with name/value fields or declarators."""
    for child in node.children:
        if child.type == CommonNodeType.VARIABLE_DECLARATOR:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node and value_node:
                val_reg = ctx.lower_expr(value_node)
                ctx.emit_inst(
                    DeclVar(
                        name=ctx.node_text(name_node),
                        value_reg=str(val_reg),
                    ),
                    node=node,
                )
            elif name_node:
                # Declaration without initializer
                val_reg = ctx.fresh_reg()
                ctx.emit_inst(
                    Const(
                        result_reg=val_reg,
                        value=ctx.constants.none_literal,
                    ),
                )
                ctx.emit_inst(
                    DeclVar(
                        name=ctx.node_text(name_node),
                        value_reg=str(val_reg),
                    ),
                    node=node,
                )
