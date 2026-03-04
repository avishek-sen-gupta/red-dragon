"""Go-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.go.expressions import (
    extract_expression_list,
    get_expression_list_children,
    lower_expression_list,
    lower_go_store_target,
)

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext

logger = logging.getLogger(__name__)


# -- Go: short variable declaration (:=) -----------------------------------


def lower_short_var_decl(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    left_names = extract_expression_list(ctx, left)
    right_regs = lower_expression_list(ctx, right)

    for name, val_reg in zip(left_names, right_regs):
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[name, val_reg],
            node=node,
        )


# -- Go: assignment statement (=) ------------------------------------------


def lower_go_assignment(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    left_nodes = get_expression_list_children(left)
    right_regs = lower_expression_list(ctx, right)

    for target, val_reg in zip(left_nodes, right_regs):
        lower_go_store_target(ctx, target, val_reg, node)


# -- Go: function declaration ----------------------------------------------


_GO_MAIN_FUNC_NAME = "main"


def lower_go_func_decl(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")

    func_name = ctx.node_text(name_node) if name_node else "__anon"

    if func_name == _GO_MAIN_FUNC_NAME:
        _lower_go_main_hoisted(ctx, body_node)
        return

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        lower_go_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST, result_reg=none_reg, operands=[ctx.constants.default_return_value]
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


def _lower_go_main_hoisted(ctx: TreeSitterEmitContext, body_node) -> None:
    """Hoist func main() body to top level so its locals land in frame 0.

    Go's ``func main()`` is the program entry point.  Rather than
    wrapping it in a function definition (which the VM would skip),
    we emit its statements directly on the top-level path.
    """
    if body_node:
        ctx.lower_block(body_node)


# -- Go: method declaration ------------------------------------------------


def lower_go_method_decl(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body_node = node.child_by_field_name("body")
    receiver_node = node.child_by_field_name("receiver")

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    # Lower receiver as parameter
    if receiver_node:
        lower_go_params(ctx, receiver_node)

    if params_node:
        lower_go_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST, result_reg=none_reg, operands=[ctx.constants.default_return_value]
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


def lower_go_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        if child.type == "parameter_declaration":
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
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
        elif child.type == "identifier":
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


# -- Go: type declaration (struct) -----------------------------------------


def lower_go_type_decl(ctx: TreeSitterEmitContext, node) -> None:
    for child in node.children:
        if child.type == "type_spec":
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            if name_node:
                type_name = ctx.node_text(name_node)
                if type_node and type_node.type == "struct_type":
                    _lower_go_struct_type(ctx, type_name, type_node, node)
                else:
                    reg = ctx.fresh_reg()
                    ctx.emit(
                        Opcode.SYMBOLIC,
                        result_reg=reg,
                        operands=[f"type:{type_name}"],
                        node=node,
                    )
                    ctx.emit(Opcode.STORE_VAR, operands=[type_name, reg])


def _lower_go_struct_type(
    ctx: TreeSitterEmitContext, type_name: str, type_node, parent_node
) -> None:
    """Emit a CLASS block for a Go struct type declaration."""
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{type_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{type_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=parent_node)
    ctx.emit(Opcode.LABEL, label=class_label)
    # Struct fields are handled at instantiation time (composite_literal)
    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[
            constants.CLASS_REF_TEMPLATE.format(name=type_name, label=class_label)
        ],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[type_name, cls_reg])


# -- Go: var declaration ---------------------------------------------------


def lower_go_var_decl(ctx: TreeSitterEmitContext, node) -> None:
    specs = [c for c in node.children if c.type == "var_spec"]
    # Handle var (...) block form: var_spec_list contains var_spec children
    spec_list = next(
        (c for c in node.children if c.type == "var_spec_list"),
        None,
    )
    if spec_list is not None:
        specs = [c for c in spec_list.children if c.type == "var_spec"]
    for spec in specs:
        _lower_var_spec(ctx, spec, node)


def _lower_var_spec(ctx: TreeSitterEmitContext, spec, parent_node) -> None:
    """Lower a single var_spec, supporting multiple names: `var a, b = 1, 2`."""
    names = [c for c in spec.children if c.type == "identifier"]
    value_node = spec.child_by_field_name("value")

    if value_node:
        val_regs = lower_expression_list(ctx, value_node)
        for name_node, val_reg in zip(names, val_regs):
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[ctx.node_text(name_node), val_reg],
                node=parent_node,
            )
        # If more names than values (e.g. `var a, b int`), store None for remainder
        for name_node in names[len(val_regs) :]:
            val_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[ctx.node_text(name_node), val_reg],
                node=parent_node,
            )
    else:
        for name_node in names:
            val_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[ctx.node_text(name_node), val_reg],
                node=parent_node,
            )


# -- Go: const declaration -------------------------------------------------


def lower_go_const_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower const_declaration: iterate const_spec children."""
    for child in node.children:
        if child.type == "const_spec":
            _lower_const_spec(ctx, child)


def _lower_const_spec(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a single const_spec: lower value, STORE_VAR."""
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    if name_node and value_node:
        val_reg = ctx.lower_expr(value_node)
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(name_node), val_reg],
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
            Opcode.STORE_VAR,
            operands=[ctx.node_text(name_node), val_reg],
            node=node,
        )
