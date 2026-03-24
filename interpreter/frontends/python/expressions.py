"""Python-specific expression lowerers -- pure functions taking (ctx, node)."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interpreter.ir import SpreadArguments, CodeLabel

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter import constants
from interpreter.frontends.common.expressions import (
    lower_const_literal,
    lower_interpolated_string_parts,
    lower_store_target as common_lower_store_target,
)
from interpreter.frontends.type_extraction import (
    extract_type_from_field,
    normalize_type_hint,
)
from interpreter.frontends.python.node_types import PythonNodeType
from interpreter.register import Register
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    Binop,
    CallFunction,
    CallMethod,
    CallUnknown,
    LoadIndex,
    StoreIndex,
    NewArray,
    NewObject,
    Symbolic,
    Branch,
    BranchIf,
    Label_,
    Return_,
)

# ── store target (with tuple unpack) ──────────────────────────


def lower_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    """Python-specific store target that adds tuple/pattern_list unpacking."""
    if target.type in (PythonNodeType.PATTERN_LIST, PythonNodeType.TUPLE_PATTERN):
        lower_tuple_unpack(ctx, target, val_reg, parent_node)
        return
    common_lower_store_target(ctx, target, val_reg, parent_node)


def lower_tuple_unpack(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    for i, child in enumerate(
        c for c in target.children if c.type != PythonNodeType.COMMA
    ):
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        elem_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadIndex(result_reg=elem_reg, arr_reg=val_reg, index_reg=idx_reg)
        )
        lower_store_target(ctx, child, elem_reg, parent_node)


# ── call ──────────────────────────────────────────────────────


def lower_call(ctx: TreeSitterEmitContext, node) -> Register:
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)

    # When a generator expression is the sole argument, tree-sitter
    # makes it the arguments node directly (not wrapped in argument_list).
    if args_node and args_node.type == PythonNodeType.GENERATOR_EXPRESSION:
        arg_regs = [ctx.lower_expr(args_node)]
    elif args_node:
        arg_regs = [
            ctx.lower_expr(c)
            for c in args_node.children
            if c.type
            not in (
                PythonNodeType.OPEN_PAREN,
                PythonNodeType.CLOSE_PAREN,
                PythonNodeType.COMMA,
            )
        ]
    else:
        arg_regs = []

    # Method call: obj.method(...)
    if func_node and func_node.type == PythonNodeType.ATTRIBUTE:
        obj_node = func_node.child_by_field_name(ctx.constants.attr_object_field)
        attr_node = func_node.child_by_field_name(ctx.constants.attr_attribute_field)
        obj_reg = ctx.lower_expr(obj_node)
        method_name = ctx.node_text(attr_node)
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
    if func_node and func_node.type == PythonNodeType.IDENTIFIER:
        func_name = ctx.node_text(func_node)
        reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(result_reg=reg, func_name=func_name, args=tuple(arg_regs)),
            node=node,
        )
        return reg

    # Dynamic / unknown call target
    target_reg = ctx.lower_expr(func_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallUnknown(result_reg=reg, target_reg=target_reg, args=tuple(arg_regs)),
        node=node,
    )
    return reg


# ── tuple ─────────────────────────────────────────────────────


def lower_tuple_literal(ctx: TreeSitterEmitContext, node) -> Register:
    elems = [
        c
        for c in node.children
        if c.type
        not in (
            PythonNodeType.OPEN_PAREN,
            PythonNodeType.CLOSE_PAREN,
            PythonNodeType.COMMA,
        )
    ]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elems))))
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint="tuple", size_reg=size_reg),
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg))
    return arr_reg


# ── conditional expression (ternary) ─────────────────────────


def lower_conditional_expr(ctx: TreeSitterEmitContext, node) -> Register:
    children = [
        c
        for c in node.children
        if c.type not in (PythonNodeType.IF_KEYWORD, PythonNodeType.ELSE_KEYWORD)
    ]
    true_expr = children[0]
    cond_expr = children[1]
    false_expr = children[2]

    cond_reg = ctx.lower_expr(cond_expr)
    true_label = ctx.fresh_label("ternary_true")
    false_label = ctx.fresh_label("ternary_false")
    end_label = ctx.fresh_label("ternary_end")

    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)))

    ctx.emit_inst(Label_(label=true_label))
    true_reg = ctx.lower_expr(true_expr)
    result_var = f"__ternary_{ctx.label_counter}"
    ctx.emit_inst(DeclVar(name=result_var, value_reg=true_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    false_reg = ctx.lower_expr(false_expr)
    ctx.emit_inst(DeclVar(name=result_var, value_reg=false_reg))
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=result_reg, name=result_var))
    return result_reg


# ── list comprehension ────────────────────────────────────────


def lower_list_comprehension(ctx: TreeSitterEmitContext, node) -> Register:
    """Desugar [expr for var in iterable if cond] into index-based loop."""
    children = [c for c in node.children if c.is_named]
    body_expr = children[0] if children else None
    for_clauses = [c for c in children if c.type == PythonNodeType.FOR_IN_CLAUSE]
    if_clauses = [c for c in children if c.type == PythonNodeType.IF_CLAUSE]

    # Create result array
    result_arr = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value="0"))
    ctx.emit_inst(
        NewArray(result_reg=result_arr, type_hint="list", size_reg=size_reg),
        node=node,
    )

    # Result index counter
    result_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=result_idx, value="0"))

    end_label = ctx.fresh_label("comp_end")

    _lower_comprehension_loop(
        ctx, for_clauses, if_clauses, body_expr, result_arr, result_idx, node, end_label
    )

    ctx.emit_inst(Label_(label=end_label))
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
    init_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_idx, value="0"))
    ctx.emit_inst(DeclVar(name="__for_idx", value_reg=init_idx))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(result_reg=len_reg, func_name="len", args=(iter_reg,)))

    loop_label = ctx.fresh_label("comp_cond")
    body_label = ctx.fresh_label("comp_body")
    loop_end_label = ctx.fresh_label("comp_loop_end")

    ctx.emit_inst(Label_(label=loop_label))
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=idx_reg, name="__for_idx"))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(Binop(result_reg=cond_reg, operator="<", left=idx_reg, right=len_reg))
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(body_label, loop_end_label))
    )

    ctx.emit_inst(Label_(label=body_label))
    # Register the loop var name as a base-level variable so that
    # declare_block_var will mangle it in the comprehension scope,
    # preventing the comprehension variable from leaking (Python 3 semantics).
    if loop_var and loop_var.type == PythonNodeType.IDENTIFIER:
        ctx._base_declared_vars.add(ctx.node_text(loop_var))
    ctx.enter_block_scope()
    elem_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadIndex(result_reg=elem_reg, arr_reg=iter_reg, index_reg=idx_reg))
    if loop_var and loop_var.type == PythonNodeType.IDENTIFIER:
        var_name = ctx.declare_block_var(ctx.node_text(loop_var))
        ctx.emit_inst(DeclVar(name=var_name, value_reg=elem_reg))
    else:
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
            ctx.emit_inst(
                BranchIf(
                    cond_reg=filter_reg,
                    branch_targets=(store_label, skip_label),
                )
            )

        ctx.emit_inst(Label_(label=store_label))
        val_reg = ctx.lower_expr(body_expr)
        ctx.emit_inst(
            StoreIndex(arr_reg=result_arr, index_reg=result_idx, value_reg=val_reg)
        )
        one_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=one_reg, value="1"))
        new_result_idx = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=new_result_idx,
                operator="+",
                left=result_idx,
                right=one_reg,
            )
        )
        ctx.emit_inst(DeclVar(name="__comp_result_idx", value_reg=new_result_idx))

        if skip_label:
            ctx.emit_inst(Label_(label=skip_label))

    ctx.exit_block_scope()

    # Increment source index
    _emit_for_increment(ctx, idx_reg, loop_label)

    ctx.emit_inst(Label_(label=loop_end_label))


# ── dict comprehension ────────────────────────────────────────


def lower_dict_comprehension(ctx: TreeSitterEmitContext, node) -> Register:
    """Desugar {k: v for var in iterable if cond} into loop."""
    children = [c for c in node.children if c.is_named]
    pair_node = next((c for c in children if c.type == PythonNodeType.PAIR), None)
    for_clause = next(
        (c for c in children if c.type == PythonNodeType.FOR_IN_CLAUSE), None
    )
    if_clauses = [c for c in children if c.type == PythonNodeType.IF_CLAUSE]

    # Create result object
    result_obj = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=result_obj, type_hint="dict"), node=node)

    # Extract loop var and iterable from for_in_clause
    clause_named = [c for c in for_clause.children if c.is_named]
    loop_var = clause_named[0] if clause_named else None
    iterable_node = clause_named[1] if len(clause_named) > 1 else None

    iter_reg = ctx.lower_expr(iterable_node) if iterable_node else ctx.fresh_reg()
    init_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_idx, value="0"))
    ctx.emit_inst(DeclVar(name="__for_idx", value_reg=init_idx))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(result_reg=len_reg, func_name="len", args=(iter_reg,)))

    loop_label = ctx.fresh_label("dcomp_cond")
    body_label = ctx.fresh_label("dcomp_body")
    end_label = ctx.fresh_label("dcomp_end")

    ctx.emit_inst(Label_(label=loop_label))
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=idx_reg, name="__for_idx"))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(Binop(result_reg=cond_reg, operator="<", left=idx_reg, right=len_reg))
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)))

    ctx.emit_inst(Label_(label=body_label))
    # Register the loop var name as a base-level variable so that
    # declare_block_var will mangle it (Python 3 comprehension scoping).
    if loop_var and loop_var.type == PythonNodeType.IDENTIFIER:
        ctx._base_declared_vars.add(ctx.node_text(loop_var))
    ctx.enter_block_scope()
    elem_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadIndex(result_reg=elem_reg, arr_reg=iter_reg, index_reg=idx_reg))
    if loop_var and loop_var.type == PythonNodeType.IDENTIFIER:
        var_name = ctx.declare_block_var(ctx.node_text(loop_var))
        ctx.emit_inst(DeclVar(name=var_name, value_reg=elem_reg))
    else:
        lower_store_target(ctx, loop_var, elem_reg, node)

    # Handle if clause (filter)
    store_label = ctx.fresh_label("dcomp_store")
    skip_label = ctx.fresh_label("dcomp_skip") if if_clauses else None
    if if_clauses:
        filter_expr = next((c for c in if_clauses[0].children if c.is_named), None)
        filter_reg = ctx.lower_expr(filter_expr)
        ctx.emit_inst(
            BranchIf(cond_reg=filter_reg, branch_targets=(store_label, skip_label))
        )

    ctx.emit_inst(Label_(label=store_label))
    # Evaluate key and value from pair
    key_node = pair_node.child_by_field_name("key") if pair_node else None
    val_node = (
        pair_node.child_by_field_name(ctx.constants.subscript_value_field)
        if pair_node
        else None
    )
    key_reg = ctx.lower_expr(key_node) if key_node else ctx.fresh_reg()
    val_reg = ctx.lower_expr(val_node) if val_node else ctx.fresh_reg()
    ctx.emit_inst(StoreIndex(arr_reg=result_obj, index_reg=key_reg, value_reg=val_reg))

    if skip_label:
        ctx.emit_inst(Label_(label=skip_label))

    ctx.exit_block_scope()

    # Increment source index
    _emit_for_increment(ctx, idx_reg, loop_label)

    ctx.emit_inst(Label_(label=end_label))
    return result_obj


# ── lambda ────────────────────────────────────────────────────


def lower_lambda(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower `lambda x, y: expr` into inline function definition."""
    func_name = f"__lambda_{ctx.label_counter}"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    # Branch past the function body
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=func_label))

    # Lower parameters
    params_node = next(
        (c for c in node.children if c.type == PythonNodeType.LAMBDA_PARAMETERS), None
    )
    if params_node:
        param_idx = 0
        for child in params_node.children:
            if _lower_python_param(ctx, child, param_idx):
                param_idx += 1

    # Lower body expression and return
    body_node = node.child_by_field_name(ctx.constants.func_body_field) or next(
        (
            c
            for c in node.children
            if c.is_named and c.type not in (PythonNodeType.LAMBDA_PARAMETERS,)
        ),
        None,
    )
    body_reg = ctx.lower_expr(body_node)
    ctx.emit_inst(Return_(value_reg=body_reg))

    ctx.emit_inst(Label_(label=end_label))

    # Reference to the lambda function
    ref_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=ref_reg, node=node)
    return ref_reg


def _lower_python_param(ctx: TreeSitterEmitContext, child, param_index: int) -> bool:
    """Lower a single Python parameter to SYMBOLIC + DECL_VAR.

    Returns True if a parameter was processed (for index counting),
    False if the child was punctuation or unrecognized.
    """
    if child.type in (
        PythonNodeType.OPEN_PAREN,
        PythonNodeType.CLOSE_PAREN,
        PythonNodeType.COMMA,
        PythonNodeType.COLON,
    ):
        return False

    default_value_node = None

    if child.type == PythonNodeType.IDENTIFIER:
        pname = ctx.node_text(child)
    elif child.type == PythonNodeType.DEFAULT_PARAMETER:
        pname_node = child.child_by_field_name(ctx.constants.func_name_field)
        if not pname_node:
            return False
        pname = ctx.node_text(pname_node)
        default_value_node = child.child_by_field_name("value")
    elif child.type == PythonNodeType.TYPED_PARAMETER:
        id_node = next(
            (sub for sub in child.children if sub.type == PythonNodeType.IDENTIFIER),
            None,
        )
        if not id_node:
            return False
        pname = ctx.node_text(id_node)
    elif child.type == PythonNodeType.TYPED_DEFAULT_PARAMETER:
        pname_node = child.child_by_field_name(ctx.constants.func_name_field)
        if not pname_node:
            return False
        pname = ctx.node_text(pname_node)
        default_value_node = child.child_by_field_name("value")
    else:
        return False

    raw_type = extract_type_from_field(ctx, child, "type")
    type_hint = normalize_type_hint(raw_type, ctx.type_map)
    param_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(result_reg=param_reg, hint=f"{constants.PARAM_PREFIX}{pname}"),
        node=child,
    )
    ctx.seed_register_type(param_reg, type_hint)
    ctx.seed_param_type(pname, type_hint)
    ctx.emit_inst(
        DeclVar(name=pname, value_reg=f"%{ctx.reg_counter - 1}"),
        node=child,
    )
    ctx.seed_var_type(pname, type_hint)

    if default_value_node:
        from interpreter.frontends.common.default_params import (
            emit_default_param_guard,
        )

        emit_default_param_guard(ctx, pname, param_index, default_value_node)

    return True


def lower_python_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower Python function parameters, handling default values."""
    param_idx = 0
    for child in params_node.children:
        if _lower_python_param(ctx, child, param_idx):
            param_idx += 1


def lower_python_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a Python function definition, handling default parameter values."""
    from interpreter.frontends.common.declarations import lower_function_def

    lower_function_def(ctx, node, params_lowerer=lower_python_params)


# ── generator expression ─────────────────────────────────────


def lower_generator_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower (expr for var in iterable) like list_comprehension but as generator."""
    children = [c for c in node.children if c.is_named]
    body_expr = children[0] if children else None
    for_clauses = [c for c in children if c.type == PythonNodeType.FOR_IN_CLAUSE]
    if_clauses = [c for c in children if c.type == PythonNodeType.IF_CLAUSE]

    result_arr = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value="0"))
    ctx.emit_inst(
        NewArray(result_reg=result_arr, type_hint="list", size_reg=size_reg),
        node=node,
    )

    result_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=result_idx, value="0"))

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

    ctx.emit_inst(Label_(label=end_label))

    # Wrap as generator call
    gen_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=gen_reg, func_name="generator", args=(result_arr,)),
        node=node,
    )
    return gen_reg


# ── set comprehension ────────────────────────────────────────


def lower_set_comprehension(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower {expr for var in iterable} as set comprehension."""
    children = [c for c in node.children if c.is_named]
    body_expr = children[0] if children else None
    for_clauses = [c for c in children if c.type == PythonNodeType.FOR_IN_CLAUSE]
    if_clauses = [c for c in children if c.type == PythonNodeType.IF_CLAUSE]

    result_obj = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=result_obj, type_hint="set"), node=node)

    result_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=result_idx, value="0"))

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

    ctx.emit_inst(Label_(label=end_label))
    return result_obj


# ── set literal ───────────────────────────────────────────────


def lower_set_literal(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower {1, 2, 3} as NEW_OBJECT('set') + STORE_INDEX per element."""
    elems = [
        c
        for c in node.children
        if c.type
        not in (
            PythonNodeType.OPEN_BRACE,
            PythonNodeType.CLOSE_BRACE,
            PythonNodeType.COMMA,
        )
    ]
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=obj_reg, type_hint="set"), node=node)
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(StoreIndex(arr_reg=obj_reg, index_reg=idx_reg, value_reg=val_reg))
    return obj_reg


# ── yield ─────────────────────────────────────────────────────


def lower_yield(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower yield expr as CALL_FUNCTION('yield', expr)."""
    named_children = [c for c in node.children if c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in named_children]
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name="yield", args=tuple(arg_regs)),
        node=node,
    )
    return reg


# ── await ─────────────────────────────────────────────────────


def lower_await(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower await expr as CALL_FUNCTION('await', expr)."""
    named_children = [c for c in node.children if c.is_named]
    arg_regs = [ctx.lower_expr(c) for c in named_children]
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=reg, func_name="await", args=tuple(arg_regs)),
        node=node,
    )
    return reg


# ── splat / spread ────────────────────────────────────────────


def lower_splat_expr(ctx: TreeSitterEmitContext, node) -> str | SpreadArguments:
    """Lower *expr (list_splat) or **expr (dictionary_splat) as CALL_FUNCTION('spread', inner)."""
    from interpreter.frontends.common.expressions import lower_spread_arg

    return lower_spread_arg(ctx, node)


# ── named expression (walrus :=) ─────────────────────────────


def lower_named_expression(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower (y := expr) as lower value, DECL_VAR name, return register."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    value_node = node.child_by_field_name(ctx.constants.subscript_value_field)
    val_reg = ctx.lower_expr(value_node)
    var_name = ctx.node_text(name_node)
    ctx.emit_inst(DeclVar(name=var_name, value_reg=val_reg), node=node)
    return val_reg


# ── slice ─────────────────────────────────────────────────────


def lower_python_subscript(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower subscript: a[idx] as LOAD_INDEX, a[1:3] as CALL_FUNCTION('slice', ...)."""
    obj_node = node.child_by_field_name(ctx.constants.subscript_value_field)
    idx_node = node.child_by_field_name(ctx.constants.subscript_index_field)
    if obj_node is None or idx_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    if idx_node.type == PythonNodeType.SLICE:
        return _lower_slice_with_collection(ctx, idx_node, obj_reg)
    idx_reg = ctx.lower_expr(idx_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=reg, arr_reg=obj_reg, index_reg=idx_reg), node=node
    )
    return reg


def _lower_slice_with_collection(
    ctx: TreeSitterEmitContext, slice_node, collection_reg: str
) -> Register:
    """Lower a[1:3] or a[1:3:2] as CALL_FUNCTION('slice', collection, start, stop, step)."""
    all_children = list(slice_node.children)
    colons = [i for i, c in enumerate(all_children) if c.type == PythonNodeType.COLON]

    start_reg = _lower_slice_none(ctx)
    stop_reg = _lower_slice_none(ctx)
    step_reg = _lower_slice_none(ctx)

    named_before_first_colon = (
        [
            c
            for c in all_children[: colons[0]]
            if c.type != PythonNodeType.COLON and c.is_named
        ]
        if colons
        else []
    )
    named_between = (
        [
            c
            for c in all_children[colons[0] + 1 : colons[1]]
            if c.type != PythonNodeType.COLON and c.is_named
        ]
        if len(colons) >= 2
        else (
            [
                c
                for c in all_children[colons[0] + 1 :]
                if c.type != PythonNodeType.COLON and c.is_named
            ]
            if colons
            else []
        )
    )
    named_after_second_colon = (
        [
            c
            for c in all_children[colons[1] + 1 :]
            if c.type != PythonNodeType.COLON and c.is_named
        ]
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
    ctx.emit_inst(
        CallFunction(
            result_reg=reg,
            func_name="slice",
            args=(collection_reg, start_reg, stop_reg, step_reg),
        ),
        node=slice_node,
    )
    return reg


def _lower_slice_none(ctx: TreeSitterEmitContext) -> Register:
    """Emit a CONST('None') for a missing slice component."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal))
    return reg


# ── no-op expression ──────────────────────────────────────────


def lower_noop_expr(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower a no-op expression node (e.g. keyword_separator, positional_separator)."""
    reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=reg, value=ctx.constants.none_literal), node=node)
    return reg


# ── list pattern ──────────────────────────────────────────────


def lower_list_pattern(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower [p1, p2, ...] pattern in match/case like a list literal."""
    elems = [
        c
        for c in node.children
        if c.type
        not in (
            PythonNodeType.OPEN_BRACKET,
            PythonNodeType.CLOSE_BRACKET,
            PythonNodeType.COMMA,
        )
    ]
    arr_reg = ctx.fresh_reg()
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value=str(len(elems))))
    ctx.emit_inst(
        NewArray(result_reg=arr_reg, type_hint="list", size_reg=size_reg),
        node=node,
    )
    for i, elem in enumerate(elems):
        val_reg = ctx.lower_expr(elem)
        idx_reg = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=idx_reg, value=str(i)))
        ctx.emit_inst(StoreIndex(arr_reg=arr_reg, index_reg=idx_reg, value_reg=val_reg))
    return arr_reg


# ── dict pattern ──────────────────────────────────────────────


def lower_dict_pattern(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower {"key": pattern, ...} in match/case as NEW_OBJECT with key/value pairs."""
    obj_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=obj_reg, type_hint="dict_pattern"), node=node)
    pairs = [
        c
        for c in node.children
        if c.is_named
        and c.type
        not in (
            PythonNodeType.OPEN_BRACE,
            PythonNodeType.CLOSE_BRACE,
            PythonNodeType.COMMA,
        )
    ]
    for pair in pairs:
        named = [ch for ch in pair.children if ch.is_named]
        if len(named) >= 2:
            key_reg = ctx.lower_expr(named[0])
            val_reg = ctx.lower_expr(named[1])
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=val_reg)
            )
        elif len(named) == 1:
            key_reg = ctx.lower_expr(named[0])
            ctx.emit_inst(
                StoreIndex(arr_reg=obj_reg, index_reg=key_reg, value_reg=key_reg)
            )
    return obj_reg


# ── f-string / interpolated string ────────────────────────────


def lower_python_string(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower string nodes, decomposing f-strings into parts + concatenation."""
    has_interpolation = any(
        c.type == PythonNodeType.INTERPOLATION for c in node.children
    )
    if not has_interpolation:
        return lower_const_literal(ctx, node)

    parts: list[str] = []
    for child in node.children:
        if child.type == PythonNodeType.INTERPOLATION:
            parts.append(lower_interpolation(ctx, child))
        elif child.type == PythonNodeType.STRING_CONTENT:
            frag_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Const(result_reg=frag_reg, value=ctx.node_text(child)), node=child
            )
            parts.append(frag_reg)
        # skip string_start, string_end delimiters

    return lower_interpolated_string_parts(ctx, parts, node)


def lower_interpolation(ctx: TreeSitterEmitContext, node) -> Register:
    """Lower {expr} inside f-strings by lowering the inner expression."""
    named_children = [
        c
        for c in node.children
        if c.is_named
        and c.type
        not in (PythonNodeType.FORMAT_SPECIFIER, PythonNodeType.TYPE_CONVERSION)
    ]
    if not named_children:
        return lower_noop_expr(ctx, node)
    return ctx.lower_expr(named_children[0])


# ── shared for-loop increment helper ─────────────────────────


def _emit_for_increment(
    ctx: TreeSitterEmitContext, idx_reg: str, loop_label: str
) -> None:
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    new_idx = ctx.fresh_reg()
    ctx.emit_inst(Binop(result_reg=new_idx, operator="+", left=idx_reg, right=one_reg))
    ctx.emit_inst(StoreVar(name="__for_idx", value_reg=new_idx))
    ctx.emit_inst(Branch(label=loop_label))
