"""Common expression lowerers — pure functions taking (ctx, node).

Extracted from BaseFrontend. Every function returns the register holding
the expression's value.
"""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.common.node_types import CommonNodeType

from interpreter.operator_kind import resolve_binop, resolve_unop
from interpreter.ir import SpreadArguments
from interpreter.types.type_expr import scalar
from interpreter.register import Register
from interpreter.var_name import VarName
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.class_name import ClassName
from interpreter.instructions import (
    Binop,
    CallFunction,
    CallMethod,
    CallUnknown,
    Const,
    LoadField,
    LoadIndex,
    LoadVar,
    NewArray,
    NewObject,
    StoreField,
    StoreIndex,
    StoreVar,
    Symbolic,
    Unop,
)


def lower_const_literal(ctx: TreeSitterEmitContext, node) -> Register:
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Const(
            result_reg=reg,
            value=ctx.node_text(node),
        ),
        node=node,
    )
    return reg


def lower_canonical_none(ctx: TreeSitterEmitContext, node) -> Register:
    """Emit canonical ``CONST "None"`` for any language's null/nil/undefined."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Const(
            result_reg=reg,
            value=ctx.constants.none_literal,
        ),
        node=node,
    )
    return reg


def lower_canonical_true(ctx: TreeSitterEmitContext, node) -> Register:
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Const(
            result_reg=reg,
            value=ctx.constants.true_literal,
        ),
        node=node,
    )
    return reg


def lower_canonical_false(ctx: TreeSitterEmitContext, node) -> Register:
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Const(
            result_reg=reg,
            value=ctx.constants.false_literal,
        ),
        node=node,
    )
    return reg


def lower_canonical_bool(ctx: TreeSitterEmitContext, node) -> Register:
    """Emit canonical True/False based on node text."""
    text = ctx.node_text(node).strip().lower()
    if text == "true":
        return lower_canonical_true(ctx, node)
    return lower_canonical_false(ctx, node)


def lower_identifier(ctx: TreeSitterEmitContext, node) -> Register:
    name = ctx.node_text(node)
    resolved_name = ctx.resolve_var(name)
    # Implicit this: bare identifier that's a class field and not a local/param
    if (
        VarName(resolved_name) not in ctx._method_declared_names
        and ctx._current_class_name
        and ctx.symbol_table.resolve_field(
            ClassName(ctx._current_class_name), FieldName(resolved_name)
        ).name.is_present()
    ):
        this_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=this_reg, name=VarName("this")), node=node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(
                result_reg=reg,
                obj_reg=this_reg,
                field_name=FieldName(resolved_name),
            ),
            node=node,
        )
        return reg
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadVar(
            result_reg=reg,
            name=VarName(resolved_name),
        ),
        node=node,
    )
    return reg


def lower_paren(ctx: TreeSitterEmitContext, node) -> Register:
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


def lower_binop(ctx: TreeSitterEmitContext, node) -> Register:
    children = [
        c
        for c in node.children
        if c.type not in (CommonNodeType.OPEN_PAREN, CommonNodeType.CLOSE_PAREN)
    ]
    lhs_reg = ctx.lower_expr(children[0])
    op = ctx.node_text(children[1])
    rhs_reg = ctx.lower_expr(children[2])
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=reg,
            operator=resolve_binop(op),
            left=lhs_reg,
            right=rhs_reg,
        ),
        node=node,
    )
    return reg


def lower_comparison(ctx: TreeSitterEmitContext, node) -> Register:
    children = [
        c
        for c in node.children
        if c.type not in (CommonNodeType.OPEN_PAREN, CommonNodeType.CLOSE_PAREN)
    ]
    lhs_reg = ctx.lower_expr(children[0])
    op = ctx.node_text(children[1])
    rhs_reg = ctx.lower_expr(children[2])
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=reg,
            operator=resolve_binop(op),
            left=lhs_reg,
            right=rhs_reg,
        ),
        node=node,
    )
    return reg


def lower_unop(ctx: TreeSitterEmitContext, node) -> Register:
    children = [
        c
        for c in node.children
        if c.type not in (CommonNodeType.OPEN_PAREN, CommonNodeType.CLOSE_PAREN)
    ]
    op = ctx.node_text(children[0])
    operand_reg = ctx.lower_expr(children[1])
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        Unop(
            result_reg=reg,
            operator=resolve_unop(op),
            operand=operand_reg,
        ),
        node=node,
    )
    return reg


def lower_call(ctx: TreeSitterEmitContext, node) -> Register:
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)
    return lower_call_impl(ctx, func_node, args_node, node)


def lower_call_impl(ctx: TreeSitterEmitContext, func_node, args_node, node) -> Register:
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
            ctx.emit_inst(
                CallMethod(
                    result_reg=reg,
                    obj_reg=obj_reg,
                    method_name=FuncName(method_name),
                    args=tuple(
                        str(a) if not isinstance(a, SpreadArguments) else a
                        for a in arg_regs
                    ),
                ),
                node=node,
            )
            return reg

    # Plain function call
    if func_node and func_node.type == CommonNodeType.IDENTIFIER:
        func_name = ctx.node_text(func_node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=reg,
                func_name=FuncName(func_name),
                args=tuple(
                    str(a) if not isinstance(a, SpreadArguments) else a
                    for a in arg_regs
                ),
            ),
            node=node,
        )
        return reg

    # Dynamic / unknown call target
    if func_node:
        target_reg = ctx.lower_expr(func_node)
    else:
        target_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Symbolic(
                result_reg=target_reg,
                hint="unknown_call_target",
            ),
        )
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallUnknown(
            result_reg=reg,
            target_reg=target_reg,
            args=tuple(
                str(a) if not isinstance(a, SpreadArguments) else a for a in arg_regs
            ),
        ),
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


def lower_attribute(ctx: TreeSitterEmitContext, node) -> Register:
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
    ctx.emit_inst(
        LoadField(
            result_reg=reg,
            obj_reg=obj_reg,
            field_name=FieldName(field_name),
        ),
        node=node,
    )
    return reg


def lower_subscript(ctx: TreeSitterEmitContext, node) -> Register:
    obj_node = node.child_by_field_name(ctx.constants.subscript_value_field)
    idx_node = node.child_by_field_name(ctx.constants.subscript_index_field)
    if obj_node is None or idx_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    idx_reg = ctx.lower_expr(idx_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(
            result_reg=reg,
            arr_reg=obj_reg,
            index_reg=idx_reg,
        ),
        node=node,
    )
    return reg


def lower_interpolated_string_parts(
    ctx: TreeSitterEmitContext, parts: list[str], node
) -> Register:
    """Chain a list of string-part registers with BINOP '+' concatenation."""
    if not parts:
        return lower_const_literal(ctx, node)
    result = parts[0]
    for part in parts[1:]:
        new_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_reg,
                operator=resolve_binop("+"),
                left=str(result),
                right=str(part),
            ),
            node=node,
        )
        result = new_reg
    return result


def lower_update_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower i++ / i-- / ++i / --i update expressions."""
    children = [c for c in node.children if c.is_named]
    if not children:
        return lower_const_literal(ctx, node)
    operand = children[0]
    text = ctx.node_text(node)
    op = "+" if "++" in text else "-"
    operand_reg = ctx.lower_expr(operand)
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result_reg,
            operator=resolve_binop(op),
            left=operand_reg,
            right=one_reg,
        ),
        node=node,
    )
    lower_store_target(ctx, operand, result_reg, node)
    return result_reg


def lower_list_literal(ctx: TreeSitterEmitContext, node) -> Register:
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
    ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elems))))
    ctx.emit_inst(
        NewArray(
            result_reg=arr_reg,
            type_hint=scalar("list"),
            size_reg=size_reg,
        ),
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(
            StoreIndex(
                arr_reg=arr_reg,
                index_reg=idx_reg,
                value_reg=(
                    val_reg if isinstance(val_reg, SpreadArguments) else val_reg
                ),
            ),
        )
    return arr_reg


def lower_dict_literal(ctx: TreeSitterEmitContext, node) -> Register:
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(
        NewObject(
            result_reg=obj_reg,
            type_hint=scalar("dict"),
        ),
        node=node,
    )
    for child in node.children:
        if child.type == CommonNodeType.PAIR:
            key_node = child.child_by_field_name("key")
            val_node = child.child_by_field_name("value")
            key_reg = ctx.lower_expr(key_node)
            val_reg = ctx.lower_expr(val_node)
            ctx.emit_inst(
                StoreIndex(
                    arr_reg=obj_reg,
                    index_reg=(
                        key_reg if isinstance(key_reg, SpreadArguments) else key_reg
                    ),
                    value_reg=(
                        val_reg if isinstance(val_reg, SpreadArguments) else val_reg
                    ),
                ),
            )
    return obj_reg


# ── common store target ──────────────────────────────────────────


def lower_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == CommonNodeType.IDENTIFIER:
        ctx.emit_inst(
            StoreVar(
                name=VarName(ctx.resolve_var(ctx.node_text(target))),
                value_reg=val_reg,
            ),
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
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_reg,
                    field_name=FieldName(ctx.node_text(attr_node)),
                    value_reg=val_reg,
                ),
                node=parent_node,
            )
    elif target.type == CommonNodeType.SUBSCRIPT:
        obj_node = target.child_by_field_name(ctx.constants.subscript_value_field)
        idx_node = target.child_by_field_name(ctx.constants.subscript_index_field)
        if obj_node and idx_node:
            obj_reg = ctx.lower_expr(obj_node)
            idx_reg = ctx.lower_expr(idx_node)
            ctx.emit_inst(
                StoreIndex(
                    arr_reg=obj_reg,
                    index_reg=idx_reg,
                    value_reg=val_reg,
                ),
                node=parent_node,
            )
    else:
        # Fallback: just store to the text of the target
        ctx.emit_inst(
            StoreVar(
                name=VarName(ctx.node_text(target)),
                value_reg=val_reg,
            ),
            node=parent_node,
        )
