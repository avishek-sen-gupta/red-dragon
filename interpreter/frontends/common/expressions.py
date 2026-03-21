"""Common expression lowerers — pure functions taking (ctx, node).

Extracted from BaseFrontend. Every function returns the register holding
the expression's value.
"""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.common.node_types import CommonNodeType

from interpreter.ir import Opcode, SpreadArguments


def lower_const_literal(ctx: TreeSitterEmitContext, node) -> str:
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.node_text(node)],
        node=node,
    )
    return reg


def lower_canonical_none(ctx: TreeSitterEmitContext, node) -> str:
    """Emit canonical ``CONST "None"`` for any language's null/nil/undefined."""
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
        node=node,
    )
    return reg


def lower_canonical_true(ctx: TreeSitterEmitContext, node) -> str:
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.true_literal],
        node=node,
    )
    return reg


def lower_canonical_false(ctx: TreeSitterEmitContext, node) -> str:
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.false_literal],
        node=node,
    )
    return reg


def lower_canonical_bool(ctx: TreeSitterEmitContext, node) -> str:
    """Emit canonical True/False based on node text."""
    text = ctx.node_text(node).strip().lower()
    if text == "true":
        return lower_canonical_true(ctx, node)
    return lower_canonical_false(ctx, node)


def lower_identifier(ctx: TreeSitterEmitContext, node) -> str:
    name = ctx.node_text(node)
    resolved_name = ctx.resolve_var(name)
    # Implicit this: bare identifier that's a class field and not a local/param
    if (
        resolved_name not in ctx._method_declared_names
        and ctx._current_class_name
        and ctx.symbol_table.resolve_field(ctx._current_class_name, resolved_name).name
    ):
        this_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"], node=node)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[this_reg, resolved_name],
            node=node,
        )
        return reg
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_VAR,
        result_reg=reg,
        operands=[resolved_name],
        node=node,
    )
    return reg


def lower_paren(ctx: TreeSitterEmitContext, node) -> str:
    inner = next(
        (
            c
            for c in node.children
            if c.type not in (CommonNodeType.OPEN_PAREN, CommonNodeType.CLOSE_PAREN)
        ),
        None,
    )
    if inner is None:
        return lower_const_literal(ctx, node)
    return ctx.lower_expr(inner)


def lower_spread_arg(ctx: TreeSitterEmitContext, node) -> SpreadArguments:
    """Lower *expr / ...expr / **expr as SpreadArguments(register).

    Returns a SpreadArguments wrapper (not a plain register string).
    The call-site lowerer includes it in CALL_FUNCTION operands;
    the VM unpacks the heap array into individual args at call time.
    """
    named_children = [c for c in node.children if c.is_named]
    inner_reg = (
        ctx.lower_expr(named_children[0])
        if named_children
        else lower_const_literal(ctx, node)
    )
    return SpreadArguments(register=inner_reg)


def lower_binop(ctx: TreeSitterEmitContext, node) -> str:
    children = [
        c
        for c in node.children
        if c.type not in (CommonNodeType.OPEN_PAREN, CommonNodeType.CLOSE_PAREN)
    ]
    lhs_reg = ctx.lower_expr(children[0])
    op = ctx.node_text(children[1])
    rhs_reg = ctx.lower_expr(children[2])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=reg,
        operands=[op, lhs_reg, rhs_reg],
        node=node,
    )
    return reg


def lower_comparison(ctx: TreeSitterEmitContext, node) -> str:
    children = [
        c
        for c in node.children
        if c.type not in (CommonNodeType.OPEN_PAREN, CommonNodeType.CLOSE_PAREN)
    ]
    lhs_reg = ctx.lower_expr(children[0])
    op = ctx.node_text(children[1])
    rhs_reg = ctx.lower_expr(children[2])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=reg,
        operands=[op, lhs_reg, rhs_reg],
        node=node,
    )
    return reg


def lower_unop(ctx: TreeSitterEmitContext, node) -> str:
    children = [
        c
        for c in node.children
        if c.type not in (CommonNodeType.OPEN_PAREN, CommonNodeType.CLOSE_PAREN)
    ]
    op = ctx.node_text(children[0])
    operand_reg = ctx.lower_expr(children[1])
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.UNOP,
        result_reg=reg,
        operands=[op, operand_reg],
        node=node,
    )
    return reg


def lower_call(ctx: TreeSitterEmitContext, node) -> str:
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    return lower_call_impl(ctx, func_node, args_node, node)


def lower_call_impl(ctx: TreeSitterEmitContext, func_node, args_node, node) -> str:
    arg_regs = extract_call_args(ctx, args_node)

    # Method call: obj.method(...)
    if func_node and func_node.type in (
        ctx.constants.attribute_node_type,
        CommonNodeType.MEMBER_EXPRESSION,
        CommonNodeType.SELECTOR_EXPRESSION,
        CommonNodeType.MEMBER_ACCESS_EXPRESSION,
        CommonNodeType.FIELD_ACCESS,
        CommonNodeType.METHOD_INDEX_EXPRESSION,
    ):
        obj_node = func_node.child_by_field_name(ctx.constants.attr_object_field)
        attr_node = func_node.child_by_field_name(ctx.constants.attr_attribute_field)
        if obj_node is None:
            obj_node = func_node.children[0] if func_node.children else None
        if attr_node is None:
            attr_node = func_node.children[-1] if len(func_node.children) > 1 else None
        if obj_node and attr_node:
            obj_reg = ctx.lower_expr(obj_node)
            method_name = ctx.node_text(attr_node)
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_METHOD,
                result_reg=reg,
                operands=[obj_reg, method_name] + arg_regs,
                node=node,
            )
            return reg

    # Plain function call
    if func_node and func_node.type == CommonNodeType.IDENTIFIER:
        func_name = ctx.node_text(func_node)
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[func_name] + arg_regs,
            node=node,
        )
        return reg

    # Dynamic / unknown call target
    if func_node:
        target_reg = ctx.lower_expr(func_node)
    else:
        target_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=target_reg,
            operands=["unknown_call_target"],
        )
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_UNKNOWN,
        result_reg=reg,
        operands=[target_reg] + arg_regs,
        node=node,
    )
    return reg


def extract_call_args(ctx: TreeSitterEmitContext, args_node) -> list[str]:
    """Extract argument registers from a call arguments node."""
    if args_node is None:
        return []
    return [
        ctx.lower_expr(c)
        for c in args_node.children
        if c.type
        not in (
            CommonNodeType.OPEN_PAREN,
            CommonNodeType.CLOSE_PAREN,
            CommonNodeType.COMMA,
            CommonNodeType.ARGUMENT,
            CommonNodeType.VALUE_ARGUMENT,
        )
        and c.is_named
    ]


def extract_call_args_unwrap(ctx: TreeSitterEmitContext, args_node) -> list[str]:
    """Extract args, unwrapping wrapper nodes like 'argument'."""
    if args_node is None:
        return []
    regs: list[str] = []
    for c in args_node.children:
        if c.type in (
            CommonNodeType.OPEN_PAREN,
            CommonNodeType.CLOSE_PAREN,
            CommonNodeType.COMMA,
        ):
            continue
        if c.type in (CommonNodeType.ARGUMENT, CommonNodeType.VALUE_ARGUMENT):
            inner = next(
                (gc for gc in c.children if gc.is_named),
                None,
            )
            if inner:
                regs.append(ctx.lower_expr(inner))
        elif c.is_named:
            regs.append(ctx.lower_expr(c))
    return regs


def lower_attribute(ctx: TreeSitterEmitContext, node) -> str:
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    attr_node = node.child_by_field_name(ctx.constants.attr_attribute_field)
    if obj_node is None:
        obj_node = node.children[0] if node.children else None
    if attr_node is None:
        attr_node = node.children[-1] if len(node.children) > 1 else None
    if obj_node is None or attr_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(attr_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def lower_subscript(ctx: TreeSitterEmitContext, node) -> str:
    obj_node = node.child_by_field_name(ctx.constants.subscript_value_field)
    idx_node = node.child_by_field_name(ctx.constants.subscript_index_field)
    if obj_node is None or idx_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    idx_reg = ctx.lower_expr(idx_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDEX,
        result_reg=reg,
        operands=[obj_reg, idx_reg],
        node=node,
    )
    return reg


def lower_interpolated_string_parts(
    ctx: TreeSitterEmitContext, parts: list[str], node
) -> str:
    """Chain a list of string-part registers with BINOP '+' concatenation."""
    if not parts:
        return lower_const_literal(ctx, node)
    result = parts[0]
    for part in parts[1:]:
        new_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=new_reg,
            operands=["+", result, part],
            node=node,
        )
        result = new_reg
    return result


def lower_update_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower i++ / i-- / ++i / --i update expressions."""
    children = [c for c in node.children if c.is_named]
    if not children:
        return lower_const_literal(ctx, node)
    operand = children[0]
    text = ctx.node_text(node)
    op = "+" if "++" in text else "-"
    operand_reg = ctx.lower_expr(operand)
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    result_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.BINOP,
        result_reg=result_reg,
        operands=[op, operand_reg, one_reg],
        node=node,
    )
    lower_store_target(ctx, operand, result_reg, node)
    return result_reg


def lower_list_literal(ctx: TreeSitterEmitContext, node) -> str:
    elems = [
        c
        for c in node.children
        if c.type
        not in (
            CommonNodeType.OPEN_BRACKET,
            CommonNodeType.CLOSE_BRACKET,
            CommonNodeType.COMMA,
        )
    ]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=arr_reg,
        operands=["list", size_reg],
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
    return arr_reg


def lower_dict_literal(ctx: TreeSitterEmitContext, node) -> str:
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=["dict"],
        node=node,
    )
    for child in node.children:
        if child.type == CommonNodeType.PAIR:
            key_node = child.child_by_field_name("key")
            val_node = child.child_by_field_name("value")
            key_reg = ctx.lower_expr(key_node)
            val_reg = ctx.lower_expr(val_node)
            ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
    return obj_reg


# ── common store target ──────────────────────────────────────────


def lower_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == CommonNodeType.IDENTIFIER:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.resolve_var(ctx.node_text(target)), val_reg],
            node=parent_node,
        )
    elif target.type in (
        ctx.constants.attribute_node_type,
        CommonNodeType.MEMBER_EXPRESSION,
        CommonNodeType.SELECTOR_EXPRESSION,
        CommonNodeType.MEMBER_ACCESS_EXPRESSION,
        CommonNodeType.FIELD_ACCESS,
    ):
        obj_node = target.child_by_field_name(ctx.constants.attr_object_field)
        attr_node = target.child_by_field_name(ctx.constants.attr_attribute_field)
        if obj_node is None:
            obj_node = target.children[0] if target.children else None
        if attr_node is None:
            attr_node = target.children[-1] if len(target.children) > 1 else None
        if obj_node and attr_node:
            obj_reg = ctx.lower_expr(obj_node)
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, ctx.node_text(attr_node), val_reg],
                node=parent_node,
            )
    elif target.type == CommonNodeType.SUBSCRIPT:
        obj_node = target.child_by_field_name(ctx.constants.subscript_value_field)
        idx_node = target.child_by_field_name(ctx.constants.subscript_index_field)
        if obj_node and idx_node:
            obj_reg = ctx.lower_expr(obj_node)
            idx_reg = ctx.lower_expr(idx_node)
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, idx_reg, val_reg],
                node=parent_node,
            )
    else:
        # Fallback: just store to the text of the target
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
