"""Go-specific expression lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

import logging
from interpreter.frontends.context import TreeSitterEmitContext

from interpreter import constants
from interpreter.frontends.common.expressions import (
    lower_const_literal,
    extract_call_args,
)
from interpreter.frontends.go.node_types import GoNodeType
from interpreter.register import Register
from interpreter.types.type_expr import scalar
from interpreter.instructions import (
    Const,
    CallFunction,
    CallMethod,
    CallUnknown,
    LoadField,
    LoadIndex,
    NewArray,
    NewObject,
    StoreField,
    StoreIndex,
    StoreVar,
    Branch,
    Label_,
    Return_,
)


def lower_go_iota(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `iota` to CONST with current iota counter value."""
    iota_val = getattr(ctx, "_go_iota_value", 0)
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=str(iota_val)), node=node)
    return reg


logger = logging.getLogger(__name__)


# -- Go: call expression ---------------------------------------------------


def lower_go_call(ctx: TreeSitterEmitContext, node) -> Register:
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)

    # Desugar make(): emit NEW_OBJECT or NEW_ARRAY based on type argument.
    # Must intercept BEFORE extract_call_args to avoid lowering type nodes as expressions.
    if (
        func_node
        and func_node.type == GoNodeType.IDENTIFIER
        and ctx.node_text(func_node) == "make"
        and args_node
    ):
        type_args = [c for c in args_node.children if c.is_named]
        if type_args:
            type_node = type_args[0]
            type_text = ctx.node_text(type_node)
            if type_node.type == "slice_type":
                reg = ctx.fresh_reg()
                size_reg = (
                    ctx.lower_expr(type_args[1])
                    if len(type_args) > 1
                    else ctx.fresh_reg()
                )
                ctx.emit_inst(
                    NewArray(
                        result_reg=reg, type_hint=scalar(type_text), size_reg=size_reg
                    ),
                    node=node,
                )
                return reg
            reg = ctx.fresh_reg()
            ctx.emit_inst(
                NewObject(result_reg=reg, type_hint=scalar(type_text)), node=node
            )
            return reg

    arg_regs = extract_call_args(ctx, args_node) if args_node else []

    # Method call via selector: obj.Method(...)
    if func_node and func_node.type == GoNodeType.SELECTOR_EXPRESSION:
        operand_node = func_node.child_by_field_name("operand")
        field_node = func_node.child_by_field_name("field")
        if operand_node and field_node:
            obj_reg = ctx.lower_expr(operand_node)
            method_name = ctx.node_text(field_node)
            reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallMethod(
                    result_reg=reg,
                    obj_reg=obj_reg,
                    method_name=method_name,
                    args=tuple(arg_regs),
                ),
                node=node,
            )
            return reg

    # Plain function call
    if func_node and func_node.type == GoNodeType.IDENTIFIER:
        func_name = ctx.node_text(func_node)

        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(result_reg=reg, func_name=func_name, args=tuple(arg_regs)),
            node=node,
        )
        return reg

    # Dynamic / unknown call
    target_reg = ctx.lower_expr(func_node) if func_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallUnknown(result_reg=reg, target_reg=target_reg, args=tuple(arg_regs)),
        node=node,
    )
    return reg


# -- Go: selector expression (obj.field) -----------------------------------


def lower_selector(ctx: TreeSitterEmitContext, node) -> Register:
    operand_node = node.child_by_field_name("operand")
    field_node = node.child_by_field_name("field")
    if operand_node is None or field_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(operand_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=field_name), node=node
    )
    return reg


# -- Go: index expression (arr[i]) -----------------------------------------


def lower_go_index(ctx: TreeSitterEmitContext, node) -> Register:
    operand_node = node.child_by_field_name("operand")
    index_node = node.child_by_field_name("index")
    if operand_node is None or index_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(operand_node)
    idx_reg = ctx.lower_expr(index_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=obj_reg, index_reg=idx_reg), node=node
    )
    return reg


# -- Go: composite literal -------------------------------------------------


def lower_composite_literal(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower Go composite literal: Point{X: 1} or []int{1, 2, 3}."""
    type_node = node.child_by_field_name("type")
    body_node = node.child_by_field_name("body") or next(
        (c for c in node.children if c.type == GoNodeType.LITERAL_VALUE), None
    )

    type_name = ctx.node_text(type_node) if type_node else "Object"
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=obj_reg, type_hint=scalar(type_name)), node=node)

    if not body_node:
        return obj_reg

    elements = [c for c in body_node.children if c.is_named]
    for i, elem in enumerate(elements):
        if elem.type == GoNodeType.KEYED_ELEMENT:
            # Key-value pair: {Key: Value}
            children = [c for c in elem.children if c.is_named]
            key_elem = children[0] if children else None
            val_elem = children[1] if len(children) > 1 else None
            key_name = (
                ctx.node_text(
                    next((c for c in key_elem.children if c.is_named), key_elem)
                )
                if key_elem
                else str(i)
            )
            val_reg = (
                ctx.lower_expr(
                    next((c for c in val_elem.children if c.is_named), val_elem)
                )
                if val_elem
                else ctx.fresh_reg()
            )
            ctx.emit_inst(
                StoreField(obj_reg=obj_reg, field_name=key_name, value_reg=val_reg),
                node=elem,
            )
        elif elem.type == GoNodeType.LITERAL_ELEMENT:
            # Positional element
            inner = next((c for c in elem.children if c.is_named), elem)
            val_reg = ctx.lower_expr(inner)
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
                node=elem,
            )
        else:
            # Direct expression element
            val_reg = ctx.lower_expr(elem)
            idx_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
                node=elem,
            )

    return obj_reg


# -- Go: type conversion expression ----------------------------------------


def lower_type_conversion(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower type_conversion_expression: []byte(s), Foo[int](y) -> CALL_FUNCTION.

    The node has a ``type`` field (the target type, e.g. ``[]byte``,
    ``generic_type``) and an ``operand`` field (the expression being converted).
    We emit CALL_FUNCTION with the type text as the function name.
    """
    type_node = node.child_by_field_name("type")
    operand_node = node.child_by_field_name("operand")
    type_name = ctx.node_text(type_node) if type_node else "unknown_type"
    operand_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name=type_name, args=(operand_reg,)),
        node=node,
    )
    return reg


# -- Go: generic type (Foo[int]) as expression reference ------------------


def lower_generic_type(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower generic_type: Foo[int] -> lower as identifier using the full text.

    When generic_type appears in expression context (e.g. inside
    type_conversion_expression), we treat it as a type name reference.
    """
    return lower_const_literal(ctx, node)


# -- Go: type assertion expression -----------------------------------------


def lower_type_assertion(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower type_assertion_expression: x.(Type) -> CALL_FUNCTION('type_assert', x, Type)."""
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_const_literal(ctx, node)
    expr_reg = ctx.lower_expr(named_children[0])
    type_text = (
        ctx.node_text(named_children[-1]) if len(named_children) > 1 else "interface{}"
    )
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg, func_name="type_assert", args=(expr_reg, type_text)
        ),
        node=node,
    )
    return reg


# -- Go: slice expression --------------------------------------------------


def _make_const(ctx: TreeSitterEmitContext, value: str) -> Register:
    """Emit a CONST and return its register."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=value))
    return reg


def lower_slice_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower slice_expression: a[low:high] -> CALL_FUNCTION('slice', a, low, high)."""
    operand_node = node.child_by_field_name("operand")
    obj_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()

    start_node = node.child_by_field_name("start")
    end_node = node.child_by_field_name("end")

    start_reg = ctx.lower_expr(start_node) if start_node else _make_const(ctx, "0")
    end_reg = (
        ctx.lower_expr(end_node)
        if end_node
        else _make_const(ctx, ctx.constants.none_literal)
    )

    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name="slice",
            args=(obj_reg, start_reg, end_reg),
        ),
        node=node,
    )
    return reg


# -- Go: func literal (anonymous function) ---------------------------------


def lower_func_literal(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower func_literal as an anonymous function."""
    from interpreter.frontends.go.declarations import lower_go_params

    func_name = f"__anon_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    ctx.emit_inst(Branch(label=end_label), node=node)
    ctx.emit_inst(Label_(label=func_label))

    if params_node:
        lower_go_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=none_reg, value=ctx.constants.default_return_value))
    ctx.emit_inst(Return_(value_reg=none_reg))
    ctx.emit_inst(Label_(label=end_label))

    reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=reg)
    return reg


# -- Go: expression list helpers -------------------------------------------


def extract_expression_list(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Extract identifiers from an expression_list node."""
    if node is None:
        return []
    if node.type == GoNodeType.EXPRESSION_LIST:
        return [
            ctx.node_text(c)
            for c in node.children
            if c.type not in (GoNodeType.COMMA,) and c.is_named
        ]
    return [ctx.node_text(node)]


def get_expression_list_children(node) -> list:
    """Get child nodes from an expression_list."""
    if node is None:
        return []
    if node.type == GoNodeType.EXPRESSION_LIST:
        return [
            c for c in node.children if c.type not in (GoNodeType.COMMA,) and c.is_named
        ]
    return [node]


def lower_expression_list(ctx: TreeSitterEmitContext, node) -> list[str]:
    """Lower each expression in an expression_list, return registers."""
    if node is None:
        return []
    if node.type == GoNodeType.EXPRESSION_LIST:
        return [
            ctx.lower_expr(c)
            for c in node.children
            if c.type not in (GoNodeType.COMMA,) and c.is_named
        ]
    return [ctx.lower_expr(node)]


# -- Go: store target with selector_expression -----------------------------


def lower_go_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == GoNodeType.IDENTIFIER:
        ctx.emit_inst(
            StoreVar(name=ctx.node_text(target), value_reg=val_reg),
            node=parent_node,
        )
    elif target.type == GoNodeType.SELECTOR_EXPRESSION:
        operand_node = target.child_by_field_name("operand")
        field_node = target.child_by_field_name("field")
        if operand_node and field_node:
            obj_reg = ctx.lower_expr(operand_node)
            ctx.emit_inst(
                StoreField(
                    obj_reg=obj_reg,
                    field_name=ctx.node_text(field_node),
                    value_reg=val_reg,
                ),
                node=parent_node,
            )
    elif target.type == GoNodeType.INDEX_EXPRESSION:
        operand_node = target.child_by_field_name("operand")
        index_node = target.child_by_field_name("index")
        if operand_node and index_node:
            obj_reg = ctx.lower_expr(operand_node)
            idx_reg = ctx.lower_expr(index_node)
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg),
                node=parent_node,
            )
    else:
        ctx.emit_inst(
            StoreVar(name=ctx.node_text(target), value_reg=val_reg),
            node=parent_node,
        )
