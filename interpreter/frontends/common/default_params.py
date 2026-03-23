"""Shared default-parameter IR emission helpers.

Provides a lazily-emitted ``__resolve_default__`` IR function and a
per-parameter guard that calls it to resolve actual-vs-default values.
"""

from __future__ import annotations

from interpreter import constants
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.ir import Opcode, CodeLabel


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

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    # param: arguments_arr
    arr_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=arr_reg,
        operands=[f"{constants.PARAM_PREFIX}arguments_arr"],
    )
    ctx.emit(Opcode.DECL_VAR, operands=["arguments_arr", arr_reg])

    # param: param_index
    idx_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=idx_reg,
        operands=[f"{constants.PARAM_PREFIX}param_index"],
    )
    ctx.emit(Opcode.DECL_VAR, operands=["param_index", idx_reg])

    # param: default_value
    def_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=def_reg,
        operands=[f"{constants.PARAM_PREFIX}default_value"],
    )
    ctx.emit(Opcode.DECL_VAR, operands=["default_value", def_reg])

    # len(arguments_arr)
    load_arr = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=load_arr, operands=["arguments_arr"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", load_arr])

    # len > param_index?
    load_idx = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=load_idx, operands=["param_index"])
    cmp_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cmp_reg, operands=[">", len_reg, load_idx])

    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[cmp_reg],
        label=CodeLabel(f"{provided_label},{use_default_label}"),
    )

    # True branch: return arguments_arr[param_index]
    ctx.emit(Opcode.LABEL, label=provided_label)
    arr2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=arr2, operands=["arguments_arr"])
    idx2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=idx2, operands=["param_index"])
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[arr2, idx2])
    ctx.emit(Opcode.RETURN, operands=[elem_reg])

    # False branch: return default_value
    ctx.emit(Opcode.LABEL, label=use_default_label)
    def2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=def2, operands=["default_value"])
    ctx.emit(Opcode.RETURN, operands=[def2])

    ctx.emit(Opcode.LABEL, label=end_label)

    ref_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=ref_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, ref_reg])


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
    ctx.emit(Opcode.LOAD_VAR, result_reg=args_reg, operands=["arguments"])

    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[param_index])

    # Call __resolve_default__(arguments, param_index, default_value)
    result_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=result_reg,
        operands=["__resolve_default__", args_reg, idx_reg, default_reg],
    )

    # Reassign the parameter variable
    ctx.emit(Opcode.STORE_VAR, operands=[param_name, result_reg])
