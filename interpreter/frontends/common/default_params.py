"""Shared default-parameter IR emission helpers.

Provides a lazily-emitted ``__resolve_default__`` IR function and a
per-parameter guard that calls it to resolve actual-vs-default values.
"""

from __future__ import annotations

from interpreter import constants
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.operator_kind import resolve_binop
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    LoadIndex,
    LoadVar,
    Return_,
    StoreVar,
    Symbolic,
)


def emit_resolve_default_func(ctx: TreeSitterEmitContext) -> None:
    """Emit the ``__resolve_default__(arguments_arr, param_index, default_value)``
    IR function exactly once.  Subsequent calls are no-ops.

    The function checks ``len(arguments_arr) > param_index`` and returns
    ``arguments_arr[param_index]`` if the caller supplied the argument,
    otherwise ``default_value``.
    """
    if ctx._resolve_default_emitted:
        return
    ctx._resolve_default_emitted = True

    func_name = "__resolve_default__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")
    provided_label = ctx.fresh_label("default_provided")
    use_default_label = ctx.fresh_label("use_default")

    ctx.emit_inst(Branch(label=end_label))
    ctx.emit_inst(Label_(label=func_label))

    # param: arguments_arr
    arr_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(
            result_reg=arr_reg,
            hint=f"{constants.PARAM_PREFIX}arguments_arr",
        ),
    )
    ctx.emit_inst(DeclVar(name="arguments_arr", value_reg=arr_reg))

    # param: param_index
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(
            result_reg=idx_reg,
            hint=f"{constants.PARAM_PREFIX}param_index",
        ),
    )
    ctx.emit_inst(DeclVar(name="param_index", value_reg=idx_reg))

    # param: default_value
    def_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Symbolic(
            result_reg=def_reg,
            hint=f"{constants.PARAM_PREFIX}default_value",
        ),
    )
    ctx.emit_inst(DeclVar(name="default_value", value_reg=def_reg))

    # len(arguments_arr)
    load_arr = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=load_arr, name="arguments_arr"))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=len_reg,
            func_name="len",
            args=(load_arr,),
        ),
    )

    # len > param_index?
    load_idx = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=load_idx, name="param_index"))
    cmp_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cmp_reg,
            operator=resolve_binop(">"),
            left=len_reg,
            right=load_idx,
        ),
    )

    ctx.emit_inst(
        BranchIf(
            cond_reg=cmp_reg,
            branch_targets=(provided_label, use_default_label),
        ),
    )

    # True branch: return arguments_arr[param_index]
    ctx.emit_inst(Label_(label=provided_label))
    arr2 = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=arr2, name="arguments_arr"))
    idx2 = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=idx2, name="param_index"))
    elem_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(
            result_reg=elem_reg,
            arr_reg=arr2,
            index_reg=idx2,
        ),
    )
    ctx.emit_inst(Return_(value_reg=elem_reg))

    # False branch: return default_value
    ctx.emit_inst(Label_(label=use_default_label))
    def2 = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=def2, name="default_value"))
    ctx.emit_inst(Return_(value_reg=def2))

    ctx.emit_inst(Label_(label=end_label))

    ref_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=ref_reg)
    ctx.emit_inst(DeclVar(name=func_name, value_reg=ref_reg))


def emit_default_param_guard(
    ctx: TreeSitterEmitContext,
    param_name: str,
    param_index: int,
    default_value_node,
) -> None:
    """Emit the per-parameter default resolution guard.

    After the normal ``SYMBOLIC`` + ``DECL_VAR`` for *param_name*, call this
    to emit IR that resolves the parameter to either the caller-provided
    argument or the evaluated default value.

    *param_index* is the absolute positional index (0-based), including
    required params that precede this one.

    *default_value_node* is the tree-sitter node for the default expression.
    """
    # Ensure __resolve_default__ is available
    emit_resolve_default_func(ctx)

    # Evaluate default value expression
    default_reg = ctx.lower_expr(default_value_node)

    # Load arguments array and param index constant
    args_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=args_reg, name="arguments"))

    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=idx_reg, value=param_index))

    # Call __resolve_default__(arguments, param_index, default_value)
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name="__resolve_default__",
            args=(args_reg, idx_reg, default_reg),
        ),
    )

    # Reassign the parameter variable
    ctx.emit_inst(StoreVar(name=param_name, value_reg=result_reg))
