"""JavaScript-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)
from interpreter.frontends.javascript.node_types import JavaScriptNodeType as JSN
from interpreter.operator_kind import resolve_binop
from interpreter.var_name import VarName
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    Binop,
    CallFunction,
    LoadIndex,
    Label_,
    Branch,
    BranchIf,
)


def lower_js_alternative(ctx: TreeSitterEmitContext, alt_node, end_label: str) -> None:
    alt_type = alt_node.type
    if alt_type == JSN.ELSE_CLAUSE:
        for child in alt_node.children:
            if child.type not in (JSN.ELSE,):
                ctx.lower_stmt(child)
    elif alt_type == JSN.IF_STATEMENT:
        lower_js_if(ctx, alt_node)
    else:
        ctx.lower_block(alt_node)


def lower_js_if(ctx: TreeSitterEmitContext, node) -> None:
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

    if alt_node:
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)),
            node=node,
        )
    else:
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(true_label, end_label)),
            node=node,
        )

    ctx.emit_inst(Label_(label=true_label))
    ctx.lower_block(body_node)
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        lower_js_alternative(ctx, alt_node, end_label)
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_for_in(ctx: TreeSitterEmitContext, node) -> None:
    # for (let x in/of obj) { body }
    operator_node = node.child_by_field_name("operator")
    is_for_of = operator_node is not None and ctx.node_text(operator_node) == "of"

    if is_for_of:
        lower_for_of(ctx, node)
        return

    # for...in — model as: keys(obj) -> index-based loop over keys array
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    obj_reg = ctx.lower_expr(right)
    keys_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=keys_reg, func_name="keys", args=(obj_reg,)),
        node=node,
    )

    is_destructure = left is not None and _is_destructuring_pattern(left)
    raw_name = (
        "__for_in_destructure"
        if is_destructure
        else (_extract_var_name(ctx, left) if left else "__for_in_var")
    )

    init_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_idx, value="0"))
    ctx.emit_inst(DeclVar(name=VarName("__for_idx"), value_reg=init_idx))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(result_reg=len_reg, func_name="len", args=(keys_reg,)))

    loop_label = ctx.fresh_label("for_in_cond")
    body_label = ctx.fresh_label("for_in_body")
    end_label = ctx.fresh_label("for_in_end")

    ctx.emit_inst(Label_(label=loop_label))
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=idx_reg, name=VarName("__for_idx")))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("<"),
            left=idx_reg,
            right=len_reg,
        )
    )
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)))

    ctx.emit_inst(Label_(label=body_label))
    ctx.enter_block_scope()
    elem_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadIndex(result_reg=elem_reg, arr_reg=keys_reg, index_reg=idx_reg))

    if is_destructure:
        _lower_for_destructure(ctx, left, elem_reg)
    else:
        var_name = ctx.declare_block_var(raw_name)
        if var_name:
            ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=elem_reg))

    update_label = ctx.fresh_label("for_in_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.exit_block_scope()

    ctx.emit_inst(Label_(label=update_label))
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    new_idx = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=new_idx, operator=resolve_binop("+"), left=idx_reg, right=one_reg
        )
    )
    ctx.emit_inst(StoreVar(name=VarName("__for_idx"), value_reg=new_idx))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_for_of(ctx: TreeSitterEmitContext, node) -> None:
    """Lower for (const x of iterable) as index-based iteration.

    Handles destructuring patterns: ``for (const [k, v] of arr)`` and
    ``for (const {x, y} of arr)`` by delegating to the existing
    array/object destructure helpers.
    """
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    iter_reg = ctx.lower_expr(right)
    is_destructure = left is not None and _is_destructuring_pattern(left)
    raw_name = (
        "__for_of_destructure"
        if is_destructure
        else (_extract_var_name(ctx, left) if left else "__for_of_var")
    )

    init_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_idx, value="0"))
    ctx.emit_inst(DeclVar(name=VarName("__for_idx"), value_reg=init_idx))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(result_reg=len_reg, func_name="len", args=(iter_reg,)))

    loop_label = ctx.fresh_label("for_of_cond")
    body_label = ctx.fresh_label("for_of_body")
    end_label = ctx.fresh_label("for_of_end")

    ctx.emit_inst(Label_(label=loop_label))
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=idx_reg, name=VarName("__for_idx")))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("<"),
            left=idx_reg,
            right=len_reg,
        )
    )
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)))

    ctx.emit_inst(Label_(label=body_label))
    ctx.enter_block_scope()
    elem_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadIndex(result_reg=elem_reg, arr_reg=iter_reg, index_reg=idx_reg))

    if is_destructure:
        _lower_for_destructure(ctx, left, elem_reg)
    else:
        var_name = ctx.declare_block_var(raw_name)
        if var_name:
            ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=elem_reg))

    update_label = ctx.fresh_label("for_of_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.exit_block_scope()

    ctx.emit_inst(Label_(label=update_label))
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    new_idx = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=new_idx, operator=resolve_binop("+"), left=idx_reg, right=one_reg
        )
    )
    ctx.emit_inst(StoreVar(name=VarName("__for_idx"), value_reg=new_idx))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def _extract_var_name(ctx: TreeSitterEmitContext, node) -> str | None:
    """Extract variable name from a declaration or identifier."""
    if node.type == JSN.IDENTIFIER:
        return ctx.node_text(node)
    if node.type in (JSN.LEXICAL_DECLARATION, JSN.VARIABLE_DECLARATION):
        for child in node.children:
            if child.type == JSN.VARIABLE_DECLARATOR:
                name_node = child.child_by_field_name(ctx.constants.func_name_field)
                if name_node:
                    return ctx.node_text(name_node)
    return None


def _is_destructuring_pattern(node) -> bool:
    """Check if node is an array_pattern or object_pattern."""
    return node.type in (JSN.ARRAY_PATTERN, JSN.OBJECT_PATTERN)


def _lower_for_destructure(
    ctx: TreeSitterEmitContext, pattern_node, elem_reg: str
) -> None:
    """Lower destructuring in a for-of/for-in loop body.

    Delegates to the existing array/object destructure helpers from
    ``javascript.declarations``.
    """
    from interpreter.frontends.javascript.declarations import (
        _lower_array_destructure,
        _lower_object_destructure,
    )

    if pattern_node.type == JSN.ARRAY_PATTERN:
        _lower_array_destructure(ctx, pattern_node, elem_reg, pattern_node)
    elif pattern_node.type == JSN.OBJECT_PATTERN:
        _lower_object_destructure(ctx, pattern_node, elem_reg, pattern_node)


def lower_js_try(ctx: TreeSitterEmitContext, node) -> None:
    body_node = node.child_by_field_name("body")
    handler = node.child_by_field_name("handler")
    finalizer = node.child_by_field_name("finalizer")
    catch_clauses = []
    if handler:
        param_node = handler.child_by_field_name("parameter")
        exc_var = ctx.node_text(param_node) if param_node else None
        catch_body = handler.child_by_field_name("body")
        catch_clauses.append({"body": catch_body, "variable": exc_var, "type": None})
    finally_node = finalizer.child_by_field_name("body") if finalizer else None
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node)


def lower_js_throw(ctx: TreeSitterEmitContext, node) -> None:
    lower_raise_or_throw(ctx, node, keyword="throw")


def lower_switch_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower switch(x) { case a: ... default: ... } as if/else chain."""
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")

    disc_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    end_label = ctx.fresh_label("switch_end")

    ctx.break_target_stack.append(end_label)

    if body_node:
        cases = [
            c
            for c in body_node.children
            if c.type in (JSN.SWITCH_CASE, JSN.SWITCH_DEFAULT)
        ]
        for case_node in cases:
            if case_node.type == JSN.SWITCH_CASE:
                value_child = case_node.child_by_field_name("value")
                if value_child:
                    case_reg = ctx.lower_expr(value_child)
                    cond_reg = ctx.fresh_reg()
                    ctx.emit_inst(
                        Binop(
                            result_reg=cond_reg,
                            operator=resolve_binop("==="),
                            left=disc_reg,
                            right=case_reg,
                        ),
                        node=case_node,
                    )
                    body_label = ctx.fresh_label("case_body")
                    next_label = ctx.fresh_label("case_next")
                    ctx.emit_inst(
                        BranchIf(
                            cond_reg=cond_reg,
                            branch_targets=(body_label, next_label),
                        )
                    )
                    ctx.emit_inst(Label_(label=body_label))
                    _lower_switch_case_body(ctx, case_node)
                    ctx.emit_inst(Branch(label=end_label))
                    ctx.emit_inst(Label_(label=next_label))
            elif case_node.type == JSN.SWITCH_DEFAULT:
                _lower_switch_case_body(ctx, case_node)

    ctx.break_target_stack.pop()
    ctx.emit_inst(Label_(label=end_label))


def _lower_switch_case_body(ctx: TreeSitterEmitContext, case_node) -> None:
    """Lower the body statements of a switch case/default clause."""
    for child in case_node.children:
        if child.is_named and child.type not in (JSN.SWITCH_CASE, JSN.SWITCH_DEFAULT):
            ctx.lower_stmt(child)


def lower_do_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower do { body } while (cond)."""
    body_node = node.child_by_field_name(ctx.constants.while_body_field)
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)

    body_label = ctx.fresh_label("do_body")
    cond_label = ctx.fresh_label("do_cond")
    end_label = ctx.fresh_label("do_end")

    ctx.emit_inst(Label_(label=body_label))

    ctx.push_loop(cond_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit_inst(Label_(label=cond_label))
    cond_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)),
        node=node,
    )
    ctx.emit_inst(Label_(label=end_label))


def lower_labeled_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `label: stmt` -> LABEL(name) + lower body."""
    label_node = node.child_by_field_name("label")
    body_node = node.child_by_field_name("body")

    label_name = ctx.node_text(label_node) if label_node else "unknown_label"
    label = ctx.fresh_label(label_name)
    ctx.emit_inst(Label_(label=label))

    if body_node:
        ctx.lower_stmt(body_node)


def lower_with_statement(ctx: TreeSitterEmitContext, node) -> None:
    """Lower `with (obj) { body }` — lower object then body."""
    object_node = node.child_by_field_name(ctx.constants.attr_object_field)
    body_node = node.child_by_field_name("body")
    if object_node:
        ctx.lower_expr(object_node)
    if body_node:
        ctx.lower_block(body_node)
