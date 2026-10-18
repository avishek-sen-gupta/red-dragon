# pyright: standard
"""Emit the singleton init block and func_init_params for a COBOL program.

Emits (in order):
  1. Init block — runs once at program load:
       NEW_OBJECT %ptr
       STORE_VAR __prog_<PID>, %ptr
       STORE_FIELD __cobol_programs, <PID>, %ptr   (the run unit's program directory)
       LABEL __ws_initial_<pid>_0        ← the initial-state block, performed
       ALLOC_REGION %ws_reg  + VALUE initialisers   by the procedure's entry
       STORE_FIELD %ptr, ws_handle, %ws_reg         after a CANCEL; at load no
       STORE_FIELD %ptr, initial_state, False       continuation is set and it
       RESUME_CONTINUATION __ws_initial_<pid>_0     falls through
       ALLOC_REGION %sr_reg  (special registers -- persistent, like WS)
       STORE_FIELD %ptr, return_code_handle, %sr_reg
       CONST %run_reg, "func_<pid>_0"       → BoundFuncRef at runtime
       STORE_FIELD %ptr, run, %run_reg
       CONST %init_reg, "func_init_params_<pid>_0"  → BoundFuncRef
       STORE_VAR __entry_<PID>, %init_reg
       BRANCH __after_<pid>_0            → skip over procedure body

  2. func_init_params function — called by _handle_call_with_memory:
       LABEL func_init_params_<pid>_0
       SYMBOLIC param:__call_arguments
       BRANCH func_<pid>_0

CANCEL sets initial_state; the procedure's entry (lower_ws_from_singleton)
then performs the initial-state block again before binding __ws_region.

Returns the after_label (CodeLabel) that CobolFrontend must emit
after the procedure body.
"""

from __future__ import annotations

from cobol_memory.region_id import RegionId
from interpreter import constants
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_data_division
from interpreter.cobol.program_object import (
    ARGUMENTS_PARAM,
    INITIAL_STATE_FIELD,
    WORKING_STORAGE_FIELD,
    entry_var,
    program_var,
)
from interpreter.cobol.run_unit import PROGRAM_DIRECTORY
from interpreter.cobol.special_registers import (
    RETURN_CODE_HANDLE,
    SPECIAL_REGISTERS_LAYOUT,
)
from interpreter.continuation_name import ContinuationName
from interpreter.field_name import FieldName
from interpreter.instructions import (
    Branch,
    BranchIf,
    Const,
    Label_,
    LoadField,
    LoadVar,
    NewObject,
    ResumeContinuation,
    SetContinuation,
    StoreField,
    StoreVar,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.types.type_expr import UNKNOWN
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

    proc_label = CodeLabel(f"func_{pid_lower}_0")
    init_params_label = CodeLabel(f"func_init_params_{pid_lower}_0")
    after_label = CodeLabel(f"__after_{pid_lower}_0")
    singleton_var = program_var(program_id)

    # --- Init block ---
    ptr_reg = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=ptr_reg))
    ctx.emit_inst(StoreVar(name=singleton_var, value_reg=ptr_reg))
    directory_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=directory_reg, name=PROGRAM_DIRECTORY))
    ctx.emit_inst(
        StoreField(
            obj_reg=directory_reg,
            field_name=FieldName(program_id.upper()),
            value_reg=ptr_reg,
        )
    )

    _lower_initial_state(ctx, program_id, ws_layout)

    # RETURN-CODE (and future special registers) get their own region, isolated
    # from WS/LS/LINKAGE/FILE so a MOVE into one cannot disturb another field's
    # layout. It is allocated HERE, once, because the register outlives a single
    # invocation: a subprogram is left in its last-used state, and a callee's
    # value must survive its own exit for the caller to copy it up.
    sr_reg = lower_data_division(
        ctx, SPECIAL_REGISTERS_LAYOUT, RegionId.SPECIAL_REGISTERS
    )
    ctx.emit_inst(
        StoreField(obj_reg=ptr_reg, field_name=RETURN_CODE_HANDLE, value_reg=sr_reg)
    )

    run_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Const.func_ref(run_reg, str(proc_label), params=[], return_type=UNKNOWN)
    )
    ctx.emit_inst(
        StoreField(obj_reg=ptr_reg, field_name=FieldName("run"), value_reg=run_reg)
    )

    init_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Const.func_ref(init_reg, str(init_params_label), params=[], return_type=UNKNOWN)
    )

    ctx.emit_inst(StoreVar(name=entry_var(program_id), value_reg=init_reg))
    ctx.emit_inst(Branch(label=after_label))

    ctx.emit_inst(Label_(label=init_params_label))
    ctx.emit_inst(
        Symbolic(
            result_reg=ctx.fresh_reg(),
            hint=f"{constants.PARAM_PREFIX}{ARGUMENTS_PARAM}",
        )
    )
    ctx.emit_inst(Branch(label=proc_label))

    return after_label


def _initial_label(program_id: str) -> CodeLabel:
    return CodeLabel(f"__ws_initial_{program_id.lower()}_0")


def _initial_continuation(program_id: str) -> ContinuationName:
    return ContinuationName(str(_initial_label(program_id)))


def _perform_initial_state(
    ctx: EmitContext, program_id: str, return_label: CodeLabel
) -> None:
    ctx.emit_inst(
        SetContinuation(
            name=_initial_continuation(program_id), target_label=return_label
        ),
        span=None,
    )
    ctx.emit_inst(Branch(label=_initial_label(program_id)), span=None)


def _lower_initial_state(
    ctx: EmitContext, program_id: str, ws_layout: DataLayout
) -> None:
    """WORKING-STORAGE allocated afresh with its VALUE clauses, and the program
    object taken out of its initial state. The init block falls through it once
    at load, with no continuation set; the procedure's entry performs it again
    after a CANCEL."""
    ctx.emit_inst(Label_(label=_initial_label(program_id)), span=None)
    ws_reg = lower_data_division(ctx, ws_layout, RegionId.WORKING_STORAGE)
    singleton_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadVar(result_reg=singleton_reg, name=program_var(program_id)), span=None
    )
    ctx.emit_inst(
        StoreField(
            obj_reg=singleton_reg, field_name=WORKING_STORAGE_FIELD, value_reg=ws_reg
        ),
        span=None,
    )
    ctx.emit_inst(
        StoreField(
            obj_reg=singleton_reg,
            field_name=INITIAL_STATE_FIELD,
            value_reg=ctx.const_to_reg(False, span=None),
        ),
        span=None,
    )
    ctx.emit_inst(ResumeContinuation(name=_initial_continuation(program_id)), span=None)


def lower_ws_from_singleton(ctx: EmitContext, program_id: str) -> None:
    """Emit load of persistent WS handle from singleton into __ws_region,
    first performing the initial-state block if a CANCEL has put the program
    object back in its initial state.

    Must be called immediately after Label_(func_<pid>_0) and before
    lower_sectioned_data_division, so __ws_region is available.
    """
    singleton_var = program_var(program_id)
    singleton_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=singleton_reg, name=singleton_var))

    _perform_initial_state_if_cancelled(ctx, program_id, singleton_reg)

    ws_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(
            result_reg=ws_reg, obj_reg=singleton_reg, field_name=WORKING_STORAGE_FIELD
        )
    )

    ctx.emit_inst(StoreVar(name=VarName("__ws_region"), value_reg=ws_reg))


def _perform_initial_state_if_cancelled(
    ctx: EmitContext, program_id: str, singleton_reg: Register
) -> None:
    initial_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(
            result_reg=initial_reg,
            obj_reg=singleton_reg,
            field_name=INITIAL_STATE_FIELD,
        ),
        span=None,
    )
    cancelled_label = CodeLabel(f"__ws_cancelled_{program_id.lower()}_0")
    ready_label = CodeLabel(f"__ws_ready_{program_id.lower()}_0")
    ctx.emit_inst(
        BranchIf(cond_reg=initial_reg, branch_targets=(cancelled_label, ready_label)),
        span=None,
    )
    ctx.emit_inst(Label_(label=cancelled_label), span=None)
    _perform_initial_state(ctx, program_id, ready_label)
    ctx.emit_inst(Label_(label=ready_label), span=None)
