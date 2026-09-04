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
from interpreter.cobol.field_extent import FieldExtent, Precision
from interpreter.cobol.region_id import RegionId
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.func_name import FuncName
from interpreter.instructions import (
    AllocRegion,
    CallWithMemory,
    Label_,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)


def _ws_extent(fl: FieldLayout) -> FieldExtent:
    """A USING parameter's slot in the caller's WORKING-STORAGE region.

    The CALL marshalling resolves each USING name with ``materialised.resolve``
    — no subscripts are in play — so the access is the field's whole declared
    range, EXACT.
    """
    return FieldExtent(
        region=RegionId.WORKING_STORAGE,
        start=fl.offset,
        length=fl.byte_length,
        precision=Precision.EXACT,
        field_name=fl.name,
    )


def _params_extent(fl: FieldLayout, offset: int) -> FieldExtent:
    """A USING parameter's slot in the freshly allocated marshalling buffer.

    That buffer becomes the callee's LINKAGE storage, so it is named as a
    LINKAGE extent. This deliberately carries NO cross-region binding: caller
    and callee extents are recorded independently and no alias edge is drawn
    between them, which is out of scope for this analysis.
    """
    return FieldExtent(
        region=RegionId.LINKAGE,
        start=offset,
        length=fl.byte_length,
        precision=Precision.EXACT,
        field_name=fl.name,
    )


def lower_call(
    ctx: EmitContext,
    stmt: CallStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CALL 'program' USING params — region-passing subprogram invocation via CallWithMemory.

    When stmt.using is non-empty:
      1. Allocate a fresh params region (sum of USING field byte lengths).
      2. Copy each USING field from WS into the params region at cumulative byte offsets.
      3. Emit CallWithMemory with params_reg pointing at the fresh region.
      4. For BY REFERENCE params, copy bytes back from the params region into WS.

    When stmt.using is empty, the caller's WS region is passed as params_reg (legacy behaviour).
    """
    _ws_layout, ws_reg = materialised.working_storage
    param_fls: list[tuple[CallUsingParam, FieldLayout]] = []

    if stmt.using:
        # Resolve field layouts for all USING params (all are in WS).
        for param in stmt.using:
            if param.omitted:
                # OMITTED: no value passed — skip entirely (red-dragon-i1rb).
                continue
            if param.is_literal:
                # Literal BY CONTENT/VALUE: no WS field to resolve.  Skip for
                # static analysis — the callee's LINKAGE slot gets no write.
                continue
            fl, _ = materialised.resolve(param.name)
            param_fls.append((param, fl))

        # Allocate fresh params region sized to total USING bytes.
        total_bytes = sum(fl.byte_length for _, fl in param_fls)
        size_reg = ctx.const_to_reg(total_bytes)
        params_reg = ctx.fresh_reg()
        ctx.emit_inst(AllocRegion(result_reg=params_reg, size_reg=size_reg))

        # Copy-in: write each USING field from WS into the params region.
        cumulative = 0
        for _, fl in param_fls:
            src_off = ctx.const_to_reg(fl.offset)
            tmp = ctx.fresh_reg()
            ctx._emit_load_region(
                result_reg=tmp,
                region_reg=ws_reg,
                offset_reg=src_off,
                length=fl.byte_length,
                extent=_ws_extent(fl),
            )
            dst_off = ctx.const_to_reg(cumulative)
            ctx._emit_write_region(
                region_reg=params_reg,
                offset_reg=dst_off,
                value_reg=tmp,
                length=fl.byte_length,
                extent=_params_extent(fl, cumulative),
            )
            cumulative += fl.byte_length
    else:
        params_reg = ws_reg

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
    # ws_reg already holds the caller's WS region (loaded at function entry), so
    # re-binding __ws_region to it is a no-op for field access but repairs the var
    # for direct readers. (Field access reloads via the singleton, so it was never
    # affected; this only matters for the shared __ws_region var.)
    ctx.emit_inst(StoreVar(name=VarName("__ws_region"), value_reg=ws_reg))

    # Copy-back: for BY REFERENCE params, write updated bytes from params region back to WS.
    if stmt.using:
        cumulative = 0
        for param, fl in param_fls:
            if param.param_type == "REFERENCE":
                src_off = ctx.const_to_reg(cumulative)
                tmp = ctx.fresh_reg()
                ctx._emit_load_region(
                    result_reg=tmp,
                    region_reg=params_reg,
                    offset_reg=src_off,
                    length=fl.byte_length,
                    extent=_params_extent(fl, cumulative),
                )
                dst_off = ctx.const_to_reg(fl.offset)
                ctx._emit_write_region(
                    region_reg=ws_reg,
                    offset_reg=dst_off,
                    value_reg=tmp,
                    length=fl.byte_length,
                    extent=_ws_extent(fl),
                )
            cumulative += fl.byte_length

    if stmt.giving and ctx.has_field(stmt.giving, materialised):
        giving_ref, giving_rr = ctx.resolve_field_ref(stmt.giving, materialised)
        str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            giving_rr,
            giving_ref.fl,
            str_reg,
            giving_ref.offset_reg,
            extent=giving_ref.extent,
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
