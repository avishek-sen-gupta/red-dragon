"""Go-specific declaration lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.go.expressions import (
    extract_expression_list,
    get_expression_list_children,
    lower_expression_list,
    lower_go_store_target,
)
from interpreter.frontends.common.declarations import make_class_ref
from interpreter.frontends.go.node_types import GoNodeType

logger = logging.getLogger(__name__)


# -- Go: short variable declaration (:=) -----------------------------------


def lower_short_var_decl(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    left_names = extract_expression_list(ctx, left)
    right_regs = lower_expression_list(ctx, right)

    for name, val_reg in zip(left_names, right_regs):
        var_name = ctx.declare_block_var(name)
        ctx.emit(
            Opcode.DECL_VAR,
            operands=[var_name, val_reg],
            node=node,
        )


# -- Go: assignment statement (=) ------------------------------------------


def lower_go_assignment(ctx: TreeSitterEmitContext, node) -> None:
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    left_nodes = get_expression_list_children(left)
    right_regs = lower_expression_list(ctx, right)

    for target, val_reg in zip(left_nodes, right_regs):
        lower_go_store_target(ctx, target, val_reg, node)


# -- Go: function declaration ----------------------------------------------

_GO_MAIN_FUNC_NAME = "main"


def lower_go_func_decl(ctx: TreeSitterEmitContext, node) -> None:
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    func_name = ctx.node_text(name_node) if name_node else "__anon"

    if func_name == _GO_MAIN_FUNC_NAME:
        _lower_go_main_hoisted(ctx, body_node)
        return

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "result")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

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
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


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
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)
    receiver_node = node.child_by_field_name("receiver")

    func_name = ctx.node_text(name_node) if name_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    raw_return = extract_type_from_field(ctx, node, "result")
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

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
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def lower_go_params(ctx: TreeSitterEmitContext, params_node) -> None:
    for child in params_node.children:
        if child.type == GoNodeType.PARAMETER_DECLARATION:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                raw_type = extract_type_from_field(ctx, child, "type")
                type_hint = normalize_type_hint(raw_type, ctx.type_map)
                param_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=param_reg,
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(param_reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[pname, f"%{ctx.reg_counter - 1}"],
                )
                ctx.seed_var_type(pname, type_hint)
        elif child.type == GoNodeType.IDENTIFIER:
            pname = ctx.node_text(child)
            ctx.emit(
                Opcode.SYMBOLIC,
                result_reg=ctx.fresh_reg(),
                operands=[f"{constants.PARAM_PREFIX}{pname}"],
                node=child,
            )
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[pname, f"%{ctx.reg_counter - 1}"],
            )


# -- Go: type declaration (struct) -----------------------------------------


def lower_go_type_decl(ctx: TreeSitterEmitContext, node) -> None:
    for child in node.children:
        if child.type == GoNodeType.TYPE_SPEC:
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            if name_node:
                type_name = ctx.node_text(name_node)
                if type_node and type_node.type == GoNodeType.STRUCT_TYPE:
                    _lower_go_struct_type(ctx, type_name, type_node, node)
                elif type_node and type_node.type == GoNodeType.INTERFACE_TYPE:
                    _lower_go_interface_type(ctx, type_name, type_node, node)
                else:
                    reg = ctx.fresh_reg()
                    ctx.emit(
                        Opcode.SYMBOLIC,
                        result_reg=reg,
                        operands=[f"type:{type_name}"],
                        node=node,
                    )
                    ctx.emit(Opcode.DECL_VAR, operands=[type_name, reg])


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
    ctx.emit(Opcode.DECL_VAR, operands=[type_name, cls_reg])


def _lower_go_interface_type(
    ctx: TreeSitterEmitContext, type_name: str, type_node, parent_node
) -> None:
    """Emit a CLASS block for a Go interface type, with method stubs seeding return types."""
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{type_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{type_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=parent_node)
    ctx.emit(Opcode.LABEL, label=class_label)

    method_elems = [c for c in type_node.children if c.type == GoNodeType.METHOD_ELEM]
    for method in method_elems:
        _lower_go_interface_method(ctx, method)

    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[make_class_ref(type_name, class_label, [])],
    )
    ctx.emit(Opcode.DECL_VAR, operands=[type_name, cls_reg])


def _lower_go_interface_method(ctx: TreeSitterEmitContext, method_node) -> None:
    """Emit a function stub for a single Go interface method_elem."""
    name_node = next(
        (c for c in method_node.children if c.type == GoNodeType.FIELD_IDENTIFIER),
        None,
    )
    method_name = ctx.node_text(name_node) if name_node else "__anon"

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{method_name}")
    end_label = ctx.fresh_label(f"end_{method_name}")

    # Return type: look for type_identifier or other type node after parameter_list(s)
    raw_return = _extract_go_method_elem_return_type(ctx, method_node)
    return_hint = normalize_type_hint(raw_return, ctx.type_map)

    ctx.emit(Opcode.BRANCH, label=end_label, node=method_node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

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
        operands=[
            constants.FUNC_REF_TEMPLATE.format(name=method_name, label=func_label)
        ],
    )
    ctx.emit(Opcode.DECL_VAR, operands=[method_name, func_reg])


def _extract_go_method_elem_return_type(ctx: TreeSitterEmitContext, method_node) -> str:
    """Extract return type from a Go interface method_elem.

    In Go's tree-sitter grammar, the return type appears as a sibling of
    parameter_list nodes — it can be a type_identifier, pointer_type,
    slice_type, etc., or a second parameter_list for multiple returns.
    """
    param_list_seen = False
    for child in method_node.children:
        if child.type == "parameter_list":
            param_list_seen = True
            continue
        if param_list_seen and child.is_named:
            return ctx.node_text(child)
    return ""


# -- Go: var declaration ---------------------------------------------------


def lower_go_var_decl(ctx: TreeSitterEmitContext, node) -> None:
    specs = [c for c in node.children if c.type == GoNodeType.VAR_SPEC]
    # Handle var (...) block form: var_spec_list contains var_spec children
    spec_list = next(
        (c for c in node.children if c.type == GoNodeType.VAR_SPEC_LIST),
        None,
    )
    if spec_list is not None:
        specs = [c for c in spec_list.children if c.type == GoNodeType.VAR_SPEC]
    for spec in specs:
        _lower_var_spec(ctx, spec, node)


def _lower_var_spec(ctx: TreeSitterEmitContext, spec, parent_node) -> None:
    """Lower a single var_spec, supporting multiple names: `var a, b = 1, 2`."""
    names = [c for c in spec.children if c.type == GoNodeType.IDENTIFIER]
    value_node = spec.child_by_field_name("value")
    raw_type = extract_type_from_field(ctx, spec, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)

    if value_node:
        val_regs = lower_expression_list(ctx, value_node)
        for name_node, val_reg in zip(names, val_regs):
            name_str = ctx.declare_block_var(ctx.node_text(name_node))
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[name_str, val_reg],
                node=parent_node,
            )
            ctx.seed_var_type(name_str, type_hint)
        # If more names than values (e.g. `var a, b int`), store None for remainder
        for name_node in names[len(val_regs) :]:
            name_str = ctx.declare_block_var(ctx.node_text(name_node))
            val_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[name_str, val_reg],
                node=parent_node,
            )
            ctx.seed_var_type(name_str, type_hint)
    else:
        for name_node in names:
            name_str = ctx.declare_block_var(ctx.node_text(name_node))
            val_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
            ctx.emit(
                Opcode.DECL_VAR,
                operands=[name_str, val_reg],
                node=parent_node,
            )
            ctx.seed_var_type(name_str, type_hint)


# -- Go: const declaration -------------------------------------------------


def lower_go_const_decl(ctx: TreeSitterEmitContext, node) -> None:
    """Lower const_declaration: iterate const_spec children."""
    for child in node.children:
        if child.type == GoNodeType.CONST_SPEC:
            _lower_const_spec(ctx, child)


def _lower_const_spec(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a single const_spec: lower value, STORE_VAR."""
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    if name_node and value_node:
        val_reg = ctx.lower_expr(value_node)
        ctx.emit(
            Opcode.DECL_VAR,
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
            Opcode.DECL_VAR,
            operands=[ctx.node_text(name_node), val_reg],
            node=node,
        )
