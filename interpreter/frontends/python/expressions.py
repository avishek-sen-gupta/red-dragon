"""Python-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.ir import Opcode
from interpreter import constants
from interpreter.frontends.common.expressions import (
    lower_const_literal,
    lower_interpolated_string_parts,
    lower_store_target as common_lower_store_target,
)

# ── store target (with tuple unpack) ──────────────────────────


def lower_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Python-specific store target that adds tuple/pattern_list unpacking."""
    if target.type in ("pattern_list", "tuple_pattern"):
        lower_tuple_unpack(ctx, target, val_reg, parent_node)
        return
    common_lower_store_target(ctx, target, val_reg, parent_node)


def lower_tuple_unpack(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    for i, child in enumerate(c for c in target.children if c.type != ","):
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        elem_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[val_reg, idx_reg],
        )
        lower_store_target(ctx, child, elem_reg, parent_node)


# ── call ──────────────────────────────────────────────────────


def lower_call(ctx: TreeSitterEmitContext, node) -> str:
    func_node = node.child_by_field_name("function")
    args_node = node.child_by_field_name("arguments")

    # When a generator expression is the sole argument, tree-sitter
    # makes it the arguments node directly (not wrapped in argument_list).
    if args_node and args_node.type == "generator_expression":
        arg_regs = [ctx.lower_expr(args_node)]
    elif args_node:
        arg_regs = [
            ctx.lower_expr(c)
            for c in args_node.children
            if c.type not in ("(", ")", ",")
        ]
    else:
        arg_regs = []

    # Method call: obj.method(...)
    if func_node and func_node.type == "attribute":
        obj_node = func_node.child_by_field_name("object")
        attr_node = func_node.child_by_field_name("attribute")
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
    if func_node and func_node.type == "identifier":
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
    target_reg = ctx.lower_expr(func_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_UNKNOWN,
        result_reg=reg,
        operands=[target_reg] + arg_regs,
        node=node,
    )
    return reg


# ── tuple ─────────────────────────────────────────────────────


def lower_tuple_literal(ctx: TreeSitterEmitContext, node) -> str:
    elems = [c for c in node.children if c.type not in ("(", ")", ",")]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=arr_reg,
        operands=["tuple", size_reg],
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
    return arr_reg


# ── conditional expression (ternary) ─────────────────────────


def lower_conditional_expr(ctx: TreeSitterEmitContext, node) -> str:
    children = [c for c in node.children if c.type not in ("if", "else")]
    true_expr = children[0]
    cond_expr = children[1]
    false_expr = children[2]

    cond_reg = ctx.lower_expr(cond_expr)
    true_label = ctx.fresh_label("ternary_true")
    false_label = ctx.fresh_label("ternary_false")
    end_label = ctx.fresh_label("ternary_end")

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{true_label},{false_label}",
    )

    ctx.emit(Opcode.LABEL, label=true_label)
    true_reg = ctx.lower_expr(true_expr)
    result_var = f"__ternary_{ctx.label_counter}"
    ctx.emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=false_label)
    false_reg = ctx.lower_expr(false_expr)
    ctx.emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    result_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=result_reg, operands=[result_var])
    return result_reg


# ── list comprehension ────────────────────────────────────────


def lower_list_comprehension(ctx: TreeSitterEmitContext, node) -> str:
    """Desugar [expr for var in iterable if cond] into index-based loop."""
    children = [c for c in node.children if c.is_named]
    body_expr = children[0] if children else None
    for_clauses = [c for c in children if c.type == "for_in_clause"]
    if_clauses = [c for c in children if c.type == "if_clause"]

    # Create result array
    result_arr = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=size_reg, operands=["0"])
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=result_arr,
        operands=["list", size_reg],
        node=node,
    )

    # Result index counter
    result_idx = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=result_idx, operands=["0"])

    end_label = ctx.fresh_label("comp_end")

    _lower_comprehension_loop(
        ctx, for_clauses, if_clauses, body_expr, result_arr, result_idx, node, end_label
    )

    ctx.emit(Opcode.LABEL, label=end_label)
    return result_arr


def _lower_comprehension_loop(
    ctx: TreeSitterEmitContext,
    for_clauses,
    if_clauses,
    body_expr,
    result_arr,
    result_idx,
    node,
    end_label,
) -> None:
    """Recursive helper: emit one level of comprehension loop."""
    if not for_clauses:
        return

    for_clause = for_clauses[0]
    remaining_fors = for_clauses[1:]

    clause_named = [c for c in for_clause.children if c.is_named]
    loop_var = clause_named[0] if clause_named else None
    iterable_node = clause_named[1] if len(clause_named) > 1 else None

    iter_reg = ctx.lower_expr(iterable_node) if iterable_node else ctx.fresh_reg()
    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("comp_cond")
    body_label = ctx.fresh_label("comp_body")
    loop_end_label = ctx.fresh_label("comp_loop_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{loop_end_label}",
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
    lower_store_target(ctx, loop_var, elem_reg, node)

    if remaining_fors:
        # Recurse for nested for-clauses (filters apply at innermost level)
        _lower_comprehension_loop(
            ctx,
            remaining_fors,
            if_clauses,
            body_expr,
            result_arr,
            result_idx,
            node,
            end_label,
        )
    else:
        # Innermost loop: apply filters and store body
        store_label = ctx.fresh_label("comp_store")
        skip_label = ctx.fresh_label("comp_skip") if if_clauses else None
        if if_clauses:
            filter_expr = next((c for c in if_clauses[0].children if c.is_named), None)
            filter_reg = ctx.lower_expr(filter_expr)
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[filter_reg],
                label=f"{store_label},{skip_label}",
            )

        ctx.emit(Opcode.LABEL, label=store_label)
        val_reg = ctx.lower_expr(body_expr)
        ctx.emit(Opcode.STORE_INDEX, operands=[result_arr, result_idx, val_reg])
        one_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_result_idx = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=new_result_idx,
            operands=["+", result_idx, one_reg],
        )
        ctx.emit(Opcode.STORE_VAR, operands=["__comp_result_idx", new_result_idx])

        if skip_label:
            ctx.emit(Opcode.LABEL, label=skip_label)

    # Increment source index
    _emit_for_increment(ctx, idx_reg, loop_label)

    ctx.emit(Opcode.LABEL, label=loop_end_label)


# ── dict comprehension ────────────────────────────────────────


def lower_dict_comprehension(ctx: TreeSitterEmitContext, node) -> str:
    """Desugar {k: v for var in iterable if cond} into loop."""
    children = [c for c in node.children if c.is_named]
    pair_node = next((c for c in children if c.type == "pair"), None)
    for_clause = next((c for c in children if c.type == "for_in_clause"), None)
    if_clauses = [c for c in children if c.type == "if_clause"]

    # Create result object
    result_obj = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=result_obj,
        operands=["dict"],
        node=node,
    )

    # Extract loop var and iterable from for_in_clause
    clause_named = [c for c in for_clause.children if c.is_named]
    loop_var = clause_named[0] if clause_named else None
    iterable_node = clause_named[1] if len(clause_named) > 1 else None

    iter_reg = ctx.lower_expr(iterable_node) if iterable_node else ctx.fresh_reg()
    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

    loop_label = ctx.fresh_label("dcomp_cond")
    body_label = ctx.fresh_label("dcomp_body")
    end_label = ctx.fresh_label("dcomp_end")

    ctx.emit(Opcode.LABEL, label=loop_label)
    cond_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cond_reg],
        label=f"{body_label},{end_label}",
    )

    ctx.emit(Opcode.LABEL, label=body_label)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
    lower_store_target(ctx, loop_var, elem_reg, node)

    # Handle if clause (filter)
    store_label = ctx.fresh_label("dcomp_store")
    skip_label = ctx.fresh_label("dcomp_skip") if if_clauses else None
    if if_clauses:
        filter_expr = next((c for c in if_clauses[0].children if c.is_named), None)
        filter_reg = ctx.lower_expr(filter_expr)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[filter_reg],
            label=f"{store_label},{skip_label}",
        )

    ctx.emit(Opcode.LABEL, label=store_label)
    # Evaluate key and value from pair
    key_node = pair_node.child_by_field_name("key") if pair_node else None
    val_node = pair_node.child_by_field_name("value") if pair_node else None
    key_reg = ctx.lower_expr(key_node) if key_node else ctx.fresh_reg()
    val_reg = ctx.lower_expr(val_node) if val_node else ctx.fresh_reg()
    ctx.emit(Opcode.STORE_INDEX, operands=[result_obj, key_reg, val_reg])

    if skip_label:
        ctx.emit(Opcode.LABEL, label=skip_label)

    # Increment source index
    _emit_for_increment(ctx, idx_reg, loop_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    return result_obj


# ── lambda ────────────────────────────────────────────────────


def lower_lambda(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `lambda x, y: expr` into inline function definition."""
    func_name = f"__lambda_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    # Branch past the function body
    ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=func_label)

    # Lower parameters
    params_node = next(
        (c for c in node.children if c.type == "lambda_parameters"), None
    )
    if params_node:
        for child in params_node.children:
            _lower_python_param(ctx, child)

    # Lower body expression and return
    body_node = node.child_by_field_name("body") or next(
        (
            c
            for c in node.children
            if c.is_named and c.type not in ("lambda_parameters",)
        ),
        None,
    )
    body_reg = ctx.lower_expr(body_node)
    ctx.emit(Opcode.RETURN, operands=[body_reg])

    ctx.emit(Opcode.LABEL, label=end_label)

    # Reference to the lambda function
    ref_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=ref_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
        node=node,
    )
    return ref_reg


def _lower_python_param(ctx: TreeSitterEmitContext, child) -> None:
    """Lower a single Python parameter to SYMBOLIC + STORE_VAR."""
    if child.type in ("(", ")", ",", ":"):
        return

    if child.type == "identifier":
        pname = ctx.node_text(child)
    elif child.type == "default_parameter":
        pname_node = child.child_by_field_name("name")
        if not pname_node:
            return
        pname = ctx.node_text(pname_node)
    elif child.type == "typed_parameter":
        id_node = next(
            (sub for sub in child.children if sub.type == "identifier"),
            None,
        )
        if not id_node:
            return
        pname = ctx.node_text(id_node)
    elif child.type == "typed_default_parameter":
        pname_node = child.child_by_field_name("name")
        if not pname_node:
            return
        pname = ctx.node_text(pname_node)
    else:
        return

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


# ── generator expression ─────────────────────────────────────


def lower_generator_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower (expr for var in iterable) like list_comprehension but as generator."""
    children = [c for c in node.children if c.is_named]
    body_expr = children[0] if children else None
    for_clauses = [c for c in children if c.type == "for_in_clause"]
    if_clauses = [c for c in children if c.type == "if_clause"]

    result_arr = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=size_reg, operands=["0"])
    ctx.emit(
        Opcode.NEW_ARRAY,
        result_reg=result_arr,
        operands=["list", size_reg],
        node=node,
    )

    result_idx = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=result_idx, operands=["0"])

    end_label = ctx.fresh_label("gen_end")

    _lower_comprehension_loop(
        ctx,
        for_clauses,
        if_clauses,
        body_expr,
        result_arr,
        result_idx,
        node,
        end_label,
    )

    ctx.emit(Opcode.LABEL, label=end_label)

    # Wrap as generator call
    gen_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=gen_reg,
        operands=["generator", result_arr],
        node=node,
    )
    return gen_reg


# ── set comprehension ────────────────────────────────────────


def lower_set_comprehension(ctx: TreeSitterEmitContext, node) -> str:
    """Lower {expr for var in iterable} as set comprehension."""
    children = [c for c in node.children if c.is_named]
    body_expr = children[0] if children else None
    for_clauses = [c for c in children if c.type == "for_in_clause"]
    if_clauses = [c for c in children if c.type == "if_clause"]

    result_obj = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=result_obj,
        operands=["set"],
        node=node,
    )

    result_idx = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=result_idx, operands=["0"])

    end_label = ctx.fresh_label("setcomp_end")

    _lower_comprehension_loop(
        ctx,
        for_clauses,
        if_clauses,
        body_expr,
        result_obj,
        result_idx,
        node,
        end_label,
    )

    ctx.emit(Opcode.LABEL, label=end_label)
    return result_obj


# ── set literal ───────────────────────────────────────────────


def lower_set_literal(ctx: TreeSitterEmitContext, node) -> str:
    """Lower {1, 2, 3} as NEW_OBJECT('set') + STORE_INDEX per element."""
    elems = [c for c in node.children if c.type not in ("{", "}", ",")]
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=["set"],
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
        ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, idx_reg, val_reg])
    return obj_reg


# ── yield ─────────────────────────────────────────────────────


def lower_yield(ctx: TreeSitterEmitContext, node) -> str:
    """Lower yield expr as CALL_FUNCTION('yield', expr)."""
    named_children = [c for c in node.children if c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in named_children]
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["yield"] + arg_regs,
        node=node,
    )
    return reg


# ── await ─────────────────────────────────────────────────────


def lower_await(ctx: TreeSitterEmitContext, node) -> str:
    """Lower await expr as CALL_FUNCTION('await', expr)."""
    named_children = [c for c in node.children if c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in named_children]
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["await"] + arg_regs,
        node=node,
    )
    return reg


# ── splat / spread ────────────────────────────────────────────


def lower_splat_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower *expr (list_splat) or **expr (dictionary_splat) as CALL_FUNCTION('spread', inner)."""
    named_children = [c for c in node.children if c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in named_children]
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["spread"] + arg_regs,
        node=node,
    )
    return reg


# ── named expression (walrus :=) ─────────────────────────────


def lower_named_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower (y := expr) as lower value, STORE_VAR name, return register."""
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")
    val_reg = ctx.lower_expr(value_node)
    var_name = ctx.node_text(name_node)
    ctx.emit(
        Opcode.STORE_VAR,
        operands=[var_name, val_reg],
        node=node,
    )
    return val_reg


# ── slice ─────────────────────────────────────────────────────


def lower_slice(ctx: TreeSitterEmitContext, node) -> str:
    """Lower a[1:3] or a[1:3:2] as CALL_FUNCTION('slice', start, stop, step)."""
    all_children = list(node.children)
    colons = [i for i, c in enumerate(all_children) if c.type == ":"]

    start_reg = _lower_slice_none(ctx)
    stop_reg = _lower_slice_none(ctx)
    step_reg = _lower_slice_none(ctx)

    named_before_first_colon = (
        [c for c in all_children[: colons[0]] if c.type != ":" and c.is_named]
        if colons
        else []
    )
    named_between = (
        [
            c
            for c in all_children[colons[0] + 1 : colons[1]]
            if c.type != ":" and c.is_named
        ]
        if len(colons) >= 2
        else (
            [c for c in all_children[colons[0] + 1 :] if c.type != ":" and c.is_named]
            if colons
            else []
        )
    )
    named_after_second_colon = (
        [c for c in all_children[colons[1] + 1 :] if c.type != ":" and c.is_named]
        if len(colons) >= 2
        else []
    )

    if named_before_first_colon:
        start_reg = ctx.lower_expr(named_before_first_colon[0])
    if named_between:
        stop_reg = ctx.lower_expr(named_between[0])
    if named_after_second_colon:
        step_reg = ctx.lower_expr(named_after_second_colon[0])

    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["slice", start_reg, stop_reg, step_reg],
        node=node,
    )
    return reg


def _lower_slice_none(ctx: TreeSitterEmitContext) -> str:
    """Emit a CONST('None') for a missing slice component."""
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=reg, operands=[ctx.constants.none_literal])
    return reg


# ── no-op expression ──────────────────────────────────────────


def lower_noop_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower a no-op expression node (e.g. keyword_separator, positional_separator)."""
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=reg,
        operands=[ctx.constants.none_literal],
        node=node,
    )
    return reg


# ── list pattern ──────────────────────────────────────────────


def lower_list_pattern(ctx: TreeSitterEmitContext, node) -> str:
    """Lower [p1, p2, ...] pattern in match/case like a list literal."""
    elems = [c for c in node.children if c.type not in ("[", "]", ",")]
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


# ── dict pattern ──────────────────────────────────────────────


def lower_dict_pattern(ctx: TreeSitterEmitContext, node) -> str:
    """Lower {"key": pattern, ...} in match/case as NEW_OBJECT with key/value pairs."""
    obj_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.NEW_OBJECT,
        result_reg=obj_reg,
        operands=["dict_pattern"],
        node=node,
    )
    pairs = [c for c in node.children if c.is_named and c.type not in ("{", "}", ",")]
    for pair in pairs:
        named = [ch for ch in pair.children if ch.is_named]
        if len(named) >= 2:
            key_reg = ctx.lower_expr(named[0])
            val_reg = ctx.lower_expr(named[1])
            ctx.emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
        elif len(named) == 1:
            key_reg = ctx.lower_expr(named[0])
            ctx.emit(
                Opcode.STORE_INDEX,
                operands=[obj_reg, key_reg, key_reg],
            )
    return obj_reg


# ── case_pattern wrapper ─────────────────────────────────────


def lower_case_pattern(ctx: TreeSitterEmitContext, node) -> str:
    """Lower a case_pattern wrapper node by lowering its inner child."""
    named_children = [c for c in node.children if c.is_named]
    if not named_children:
        return lower_noop_expr(ctx, node)
    return ctx.lower_expr(named_children[0])


# ── f-string / interpolated string ────────────────────────────


def lower_python_string(ctx: TreeSitterEmitContext, node) -> str:
    """Lower string nodes, decomposing f-strings into parts + concatenation."""
    has_interpolation = any(c.type == "interpolation" for c in node.children)
    if not has_interpolation:
        return lower_const_literal(ctx, node)

    parts: list[str] = []
    for child in node.children:
        if child.type == "interpolation":
            parts.append(lower_interpolation(ctx, child))
        elif child.type == "string_content":
            frag_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CONST,
                result_reg=frag_reg,
                operands=[ctx.node_text(child)],
                node=child,
            )
            parts.append(frag_reg)
        # skip string_start, string_end delimiters

    return lower_interpolated_string_parts(ctx, parts, node)


def lower_interpolation(ctx: TreeSitterEmitContext, node) -> str:
    """Lower {expr} inside f-strings by lowering the inner expression."""
    named_children = [
        c
        for c in node.children
        if c.is_named and c.type not in ("format_specifier", "type_conversion")
    ]
    if not named_children:
        return lower_noop_expr(ctx, node)
    return ctx.lower_expr(named_children[0])


# ── shared for-loop increment helper ─────────────────────────


def _emit_for_increment(
    ctx: TreeSitterEmitContext, idx_reg: str, loop_label: str
) -> None:
    one_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
    new_idx = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
    ctx.emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
    idx_reload = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=idx_reload, operands=["__for_idx"])
    ctx.emit(Opcode.BRANCH, label=loop_label)
