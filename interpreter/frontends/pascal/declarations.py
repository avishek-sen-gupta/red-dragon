"""Pascal-specific declaration lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.pascal.pascal_constants import KEYWORD_NOISE
from interpreter.frontends.pascal.control_flow import lower_pascal_block
from interpreter.frontends.type_extraction import (
    normalize_type_hint,
)
from interpreter.frontends.pascal.type_helpers import extract_pascal_return_type
from interpreter.frontends.pascal.node_types import PascalNodeType

logger = logging.getLogger(__name__)


def lower_pascal_assignment(ctx: TreeSitterEmitContext, node) -> None:
    """Lower assignment -- children: target, kAssign, expression."""
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if len(named_children) < 2:
        logger.warning(
            "Pascal assignment with fewer than 2 named children at %s",
            ctx.source_loc(node),
        )
        return
    target = named_children[0]
    value = named_children[-1]
    val_reg = ctx.lower_expr(value)
    if target.type == PascalNodeType.EXPR_SUBSCRIPT:
        target_named = [
            c for c in target.children if c.is_named and c.type not in KEYWORD_NOISE
        ]
        if target_named:
            obj_reg = ctx.lower_expr(target_named[0])
            args_node = next(
                (c for c in target.children if c.type == PascalNodeType.EXPR_ARGS), None
            )
            if args_node:
                idx_children = [
                    c
                    for c in args_node.children
                    if c.is_named and c.type not in KEYWORD_NOISE
                ]
                idx_reg = (
                    ctx.lower_expr(idx_children[0]) if idx_children else ctx.fresh_reg()
                )
            else:
                idx_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, idx_reg, val_reg],
                node=node,
            )
        else:
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[ctx.node_text(target), val_reg],
                node=node,
            )
    elif target.type == PascalNodeType.EXPR_DOT:
        dot_named = [
            c for c in target.children if c.is_named and c.type not in KEYWORD_NOISE
        ]
        obj_reg = ctx.lower_expr(dot_named[0])
        field_name = ctx.node_text(dot_named[-1])
        ctx.emit(
            Opcode.STORE_FIELD,
            operands=[obj_reg, field_name, val_reg],
            node=node,
        )
    else:
        target_name = ctx.node_text(target)
        current_function_name = getattr(ctx, "_pascal_current_function_name", "")
        if current_function_name and target_name == current_function_name:
            ctx.emit(Opcode.RETURN, operands=[val_reg], node=node)
        else:
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[target_name, val_reg],
                node=node,
            )


def lower_pascal_decl_vars(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declVars -- contains multiple declVar children."""
    for child in node.children:
        if child.type == PascalNodeType.DECL_VAR:
            lower_pascal_decl_var(ctx, child)


def lower_pascal_decl_var(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declVar -- identifier : type.

    Array types emit NEW_ARRAY; scalar types default to NONE_LITERAL.
    """
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    if id_node is None:
        return
    var_name = ctx.node_text(id_node)
    type_node = next((c for c in node.children if c.type == PascalNodeType.TYPE), None)
    array_size = _pascal_array_size(ctx, type_node) if type_node else 0
    if array_size > 0:
        size_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(array_size)])
        arr_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["array", size_reg],
            node=node,
        )
        ctx.emit(Opcode.STORE_VAR, operands=[var_name, arr_reg], node=node)
    else:
        type_name = _pascal_var_type_name(ctx, type_node) if type_node else ""
        type_hint = (
            normalize_type_hint(type_name.lower(), ctx.type_map) if type_name else ""
        )
        val_reg = ctx.fresh_reg()
        record_types: set[str] = getattr(ctx, "_pascal_record_types", set())
        if type_name in record_types:
            ctx.emit(
                Opcode.CALL_FUNCTION,
                result_reg=val_reg,
                operands=[type_name],
                node=node,
            )
        else:
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
            )
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[var_name, val_reg],
            node=node,
        )
        ctx.seed_var_type(var_name, type_hint)


def _pascal_array_size(ctx: TreeSitterEmitContext, type_node) -> int:
    """Extract array size from a Pascal type node containing declArray."""
    decl_array = next(
        (c for c in type_node.children if c.type == PascalNodeType.DECL_ARRAY), None
    )
    if decl_array is None:
        return 0
    range_node = next(
        (c for c in decl_array.children if c.type == PascalNodeType.RANGE), None
    )
    if range_node is None:
        return 0
    nums = [c for c in range_node.children if c.type == PascalNodeType.LITERAL_NUMBER]
    if len(nums) < 2:
        return 0
    try:
        lo = int(ctx.node_text(nums[0]))
        hi = int(ctx.node_text(nums[1]))
        return hi - lo + 1
    except ValueError:
        return 0


def _pascal_var_type_name(ctx: TreeSitterEmitContext, type_node) -> str:
    """Extract the type name from a Pascal type node (type > typeref > identifier)."""
    typeref = next(
        (c for c in type_node.children if c.type == PascalNodeType.TYPEREF), None
    )
    if typeref is None:
        return ""
    id_node = next(
        (c for c in typeref.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    return ctx.node_text(id_node) if id_node else ""


def lower_pascal_proc(ctx: TreeSitterEmitContext, node) -> None:
    """Lower defProc/declProc -- contains kFunction/kProcedure, identifier, declArgs, type, block.

    For ``defProc`` nodes the identifier and declArgs live inside a
    nested ``declProc`` child; for standalone ``declProc`` nodes they
    are direct children.
    """
    decl_node = next(
        (c for c in node.children if c.type == PascalNodeType.DECL_PROC), None
    )
    search_node = decl_node if decl_node else node
    id_node = next(
        (c for c in search_node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    args_node = next(
        (c for c in search_node.children if c.type == PascalNodeType.DECL_ARGS), None
    )
    body_node = next((c for c in node.children if c.type == PascalNodeType.BLOCK), None)

    func_name = ctx.node_text(id_node) if id_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_pascal_return_type(ctx, search_node)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if args_node:
        _lower_pascal_params(ctx, args_node)

    prev_func_name = getattr(ctx, "_pascal_current_function_name", "")
    ctx._pascal_current_function_name = func_name
    for child in node.children:
        if child.type == PascalNodeType.DEF_PROC:
            lower_pascal_proc(ctx, child)
    if body_node:
        lower_pascal_block(ctx, body_node)
    ctx._pascal_current_function_name = prev_func_name

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


def _lower_pascal_params(ctx: TreeSitterEmitContext, args_node) -> None:
    """Lower declArgs -- contains declArg children with identifier and typeref."""
    for child in args_node.children:
        if child.type in KEYWORD_NOISE:
            continue
        if child.type == PascalNodeType.DECL_ARG:
            _lower_pascal_single_param(ctx, child)
        elif child.type == PascalNodeType.IDENTIFIER:
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


def _lower_pascal_single_param(ctx: TreeSitterEmitContext, child) -> None:
    """Lower a single declArg -- extract all identifier names.

    Pascal allows multiple identifiers sharing a type in one declArg,
    e.g. ``a, b: integer``.  Only direct ``identifier`` children are
    parameter names; the type identifier is nested inside ``type > typeref``.
    """
    type_name = _pascal_var_type_name(
        ctx, next((c for c in child.children if c.type == PascalNodeType.TYPE), None)
    )
    type_hint = (
        normalize_type_hint(type_name.lower(), ctx.type_map) if type_name else ""
    )
    for id_node in child.children:
        if id_node.type != PascalNodeType.IDENTIFIER:
            continue
        pname = ctx.node_text(id_node)
        _sym_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=_sym_reg,
            operands=[f"{constants.PARAM_PREFIX}{pname}"],
            node=child,
        )
        ctx.seed_register_type(_sym_reg, type_hint)
        ctx.seed_param_type(pname, type_hint)
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[pname, f"%{ctx.reg_counter - 1}"],
        )
        ctx.seed_var_type(pname, type_hint)


def lower_pascal_decl_consts(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declConsts -- iterate declConst children."""
    for child in node.children:
        if child.type == PascalNodeType.DECL_CONST:
            lower_pascal_decl_const(ctx, child)


def lower_pascal_decl_const(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declConst -- extract name + defaultValue child, lower value, STORE_VAR."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    if id_node is None:
        return
    var_name = ctx.node_text(id_node)
    value_node = next(
        (c for c in node.children if c.type == PascalNodeType.DEFAULT_VALUE), None
    )
    if value_node:
        # defaultValue wraps the actual expression
        inner = next(
            (
                c
                for c in value_node.children
                if c.is_named and c.type not in KEYWORD_NOISE
            ),
            None,
        )
        val_reg = ctx.lower_expr(inner) if inner else ctx.fresh_reg()
        if inner is None:
            ctx.emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[ctx.constants.none_literal],
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
    )


def lower_pascal_decl_types(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declTypes -- iterate individual declType children."""
    for child in node.children:
        if child.type == PascalNodeType.DECL_TYPE:
            lower_pascal_decl_type(ctx, child)


def lower_pascal_decl_type(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declType -- emit CLASS_REF for record types, skip others."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    class_node = next(
        (c for c in node.children if c.type == PascalNodeType.DECL_CLASS), None
    )

    if id_node is None or class_node is None:
        return

    # Only handle record types
    has_record = any(c.type == PascalNodeType.K_RECORD for c in class_node.children)
    if not has_record:
        return

    type_name = ctx.node_text(id_node)
    record_types: set[str] = getattr(ctx, "_pascal_record_types", set())
    record_types.add(type_name)
    ctx._pascal_record_types = record_types
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{type_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{type_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)
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
