# pyright: standard
"""Emit the singleton init block and func_init_params for a COBOL program.

Emits (in order):
  1. Init block — runs once at program load:
       NEW_OBJECT %ptr
       CONST %size_reg, <ws_size>
       ALLOC_REGION %ws_reg, %size_reg  + VALUE initialisers
       STORE_FIELD %ptr, ws_handle, %ws_reg
       CONST %run_reg, "func_<pid>_0"       → BoundFuncRef at runtime
       STORE_FIELD %ptr, run, %run_reg
       CONST %init_reg, "func_init_params_<pid>_0"  → BoundFuncRef
       STORE_FIELD %ptr, __init_params__, %init_reg
       STORE_VAR __prog_<PID>, %ptr
       BRANCH __after_<pid>_0            → skip over procedure body

  2. func_init_params function — called by _handle_call_with_memory:
       LABEL func_init_params_<pid>_0
       BRANCH func_<pid>_0               → __params_region/__results_region
                                           already injected by handler

Returns the after_label (CodeLabel) that CobolFrontend must emit
after the procedure body.
"""

from __future__ import annotations

from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_data_division
from interpreter.field_name import FieldName
from interpreter.instructions import (
    Branch,
    Const,
    Label_,
    LoadField,
    LoadVar,
    NewObject,
    StoreField,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.var_name import VarName


def lower_program_init(
    ctx: EmitContext,
    program_id: str,
    ws_layout: DataLayout,
) -> CodeLabel:
    """Emit the singleton init block and func_init_params function.

    Returns the after_label. CobolFrontend must emit Label_(after_label)
    after the procedure body.
    """
    pid_lower = program_id.lower()
    pid_upper = program_id.upper()

    proc_label = CodeLabel(f"func_{pid_lower}_0")
    init_params_label = CodeLabel(f"func_init_params_{pid_lower}_0")
    after_label = CodeLabel(f"__after_{pid_lower}_0")
    singleton_var = VarName(f"__prog_{pid_upper}")

    # --- Init block ---
    ptr_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=ptr_reg))

    ws_reg = lower_data_division(ctx, ws_layout)

    ctx.emit_inst(
        StoreField(obj_reg=ptr_reg, field_name=FieldName("ws_handle"), value_reg=ws_reg)
    )

    run_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=run_reg, value=str(proc_label)))
    ctx.emit_inst(
        StoreField(obj_reg=ptr_reg, field_name=FieldName("run"), value_reg=run_reg)
    )

    init_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_reg, value=str(init_params_label)))
    ctx.emit_inst(
        StoreField(
            obj_reg=ptr_reg, field_name=FieldName("__init_params__"), value_reg=init_reg
        )
    )

    ctx.emit_inst(StoreVar(name=singleton_var, value_reg=ptr_reg))
    ctx.emit_inst(Branch(label=after_label))

    # --- func_init_params function ---
    # __params_region and __results_region are injected by _handle_call_with_memory
    ctx.emit_inst(Label_(label=init_params_label))
    ctx.emit_inst(Branch(label=proc_label))

    return after_label


def lower_ws_from_singleton(ctx: EmitContext, program_id: str) -> None:
    """Emit load of persistent WS handle from singleton into __ws_region.

    Must be called immediately after Label_(func_<pid>_0) and before
    lower_sectioned_data_division, so __ws_region is available.
    """
    pid_upper = program_id.upper()

    singleton_var = VarName(f"__prog_{pid_upper}")
    singleton_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=singleton_reg, name=singleton_var))

    ws_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(
            result_reg=ws_reg, obj_reg=singleton_reg, field_name=FieldName("ws_handle")
        )
    )

    ctx.emit_inst(StoreVar(name=VarName("__ws_region"), value_reg=ws_reg))
