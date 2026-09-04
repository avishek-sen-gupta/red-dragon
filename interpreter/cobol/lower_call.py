"""CALL, ALTER, ENTRY, CANCEL statement lowering."""

from __future__ import annotations

import logging

from cobol_asg.cobol_statements import (
    AlterStatement,
    CallStatement,
    CallUsingParam,
    CancelStatement,
    EntryStatement,
)
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import (
    AllocRegion,
    CallWithMemory,
    Label_,
    LoadRegion,
    StoreVar,
    WriteRegion,
)
from interpreter.ir import CodeLabel
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)


def lower_call(
    ctx: EmitContext,
    stmt: CallStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CALL 'program' USING params — region-passing subprogram invocation via CallWithMemory.

    When stmt.using is non-empty:
      1. Allocate a fresh params region (sum of USING field byte lengths).
      2. Copy each USING field from ITS OWN section's region into the params
         region at cumulative byte offsets. An argument may be declared in
         LINKAGE or LOCAL-STORAGE -- passing a LINKAGE item on to a further
         CALL is the ordinary "hand my caller's parameter down" chain -- so the
         region comes from materialised.resolve, never from a section chosen here.
      3. Emit CallWithMemory with params_reg pointing at the fresh region.
      4. For BY REFERENCE params, copy bytes back from the params region into
         that same owning region.

    When stmt.using is empty, the caller's WS region is passed as params_reg (legacy behaviour).
    """
    param_fls: list[tuple[CallUsingParam, FieldLayout, Register]] = []

    if stmt.using:
        for param in stmt.using:
            if param.omitted:
                # OMITTED: no value passed — skip entirely (red-dragon-i1rb).
                continue
            if param.is_literal:
                # Literal BY CONTENT/VALUE: no WS field to resolve.  Skip for
                # static analysis — the callee's LINKAGE slot gets no write.
                continue
            fl, owning_reg = materialised.resolve(param.name)
            param_fls.append((param, fl, owning_reg))

        # Allocate fresh params region sized to total USING bytes.
        total_bytes = sum(fl.byte_length for _, fl, _ in param_fls)
        size_reg = ctx.const_to_reg(total_bytes)
        params_reg = ctx.fresh_reg()
        ctx.emit_inst(AllocRegion(result_reg=params_reg, size_reg=size_reg))

        # Copy-in: write each USING field from WS into the params region.
        cumulative = 0
        for _, fl, owning_reg in param_fls:
            src_off = ctx.const_to_reg(fl.offset)
            tmp = ctx.fresh_reg()
            ctx.emit_inst(
                LoadRegion(
                    result_reg=tmp,
                    region_reg=owning_reg,
                    offset_reg=src_off,
                    length=fl.byte_length,
                )
            )
            dst_off = ctx.const_to_reg(cumulative)
            ctx.emit_inst(
                WriteRegion(
                    region_reg=params_reg,
                    offset_reg=dst_off,
                    length=fl.byte_length,
                    value_reg=tmp,
                )
            )
            cumulative += fl.byte_length
    else:
        _ws_layout, params_reg = materialised.working_storage

    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallWithMemory(
            result_reg=result_reg,
            func_name=FuncName(stmt.program),
            params_reg=params_reg,
            results_reg=params_reg,
        )
    )

    # Restore the caller's __ws_region binding. CallWithMemory dispatches into the
    # callee's func_init_params, whose body re-binds the shared __ws_region var to
    # the CALLEE's WS region. When the callee frame is popped on EXIT PROGRAM the
    # caller's __ws_region binding does not reliably survive, so consumers that
    # read __ws_region directly (e.g. CICS SEND/RECEIVE MAP via
    # _get_ws_region_addr) would otherwise see the callee's region after the CALL.
    # caller_ws_reg holds the caller's WS region (loaded at function entry), so
    # re-binding __ws_region to it is a no-op for field access but repairs the var
    # for direct readers. (Field access reloads via the singleton, so it was never
    # affected; this only matters for the shared __ws_region var.)
    _ws_layout, caller_ws_reg = materialised.working_storage
    ctx.emit_inst(StoreVar(name=VarName("__ws_region"), value_reg=caller_ws_reg))

    # Copy-back: for BY REFERENCE params, write updated bytes from params region back to WS.
    if stmt.using:
        cumulative = 0
        for param, fl, owning_reg in param_fls:
            if param.param_type == "REFERENCE":
                src_off = ctx.const_to_reg(cumulative)
                tmp = ctx.fresh_reg()
                ctx.emit_inst(
                    LoadRegion(
                        result_reg=tmp,
                        region_reg=params_reg,
                        offset_reg=src_off,
                        length=fl.byte_length,
                    )
                )
                dst_off = ctx.const_to_reg(fl.offset)
                ctx.emit_inst(
                    WriteRegion(
                        region_reg=owning_reg,
                        offset_reg=dst_off,
                        length=fl.byte_length,
                        value_reg=tmp,
                    )
                )
            cumulative += fl.byte_length

    if stmt.giving and ctx.has_field(stmt.giving, materialised):
        giving_ref, giving_rr = ctx.resolve_field_ref(stmt.giving, materialised)
        str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            giving_rr, giving_ref.fl, str_reg, giving_ref.offset_reg
        )

    logger.info(
        "CALL %s with %d params (CallWithMemory)", stmt.program, len(stmt.using)
    )


def lower_alter(
    ctx: EmitContext,
    stmt: AlterStatement,
    _materialised: MaterialisedSectionedLayout,
) -> None:
    """ALTER para-1 TO PROCEED TO para-2."""
    for pt in stmt.proceed_tos:
        target_reg = ctx.const_to_reg(f"para_{pt.target}")
        ctx.emit_inst(
            StoreVar(
                name=VarName(f"__alter_{pt.source}"),
                value_reg=target_reg,
            )
        )
        logger.info("ALTER %s TO PROCEED TO %s", pt.source, pt.target)


def lower_entry(
    ctx: EmitContext,
    stmt: EntryStatement,
    _materialised: MaterialisedSectionedLayout,
) -> None:
    """ENTRY 'name' — alternate entry point for a subprogram."""
    if stmt.entry_name:
        ctx.emit_inst(Label_(label=CodeLabel(f"entry_{stmt.entry_name}")))
        logger.info("ENTRY %s", stmt.entry_name)


def lower_cancel(
    _ctx: EmitContext,
    stmt: CancelStatement,
    _materialised: MaterialisedSectionedLayout,
) -> None:
    """CANCEL program — no-op for static analysis."""
    for prog in stmt.programs:
        logger.info("CANCEL %s (no-op for static analysis)", prog)
