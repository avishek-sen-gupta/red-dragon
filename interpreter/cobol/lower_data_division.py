"""DATA DIVISION lowering — allocate region and initialize field values."""

from __future__ import annotations

import logging

from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import whole_field_extent
from interpreter.cobol.region_id import RegionId
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    SectionedLayout,
)
from interpreter.cobol.special_registers import (
    RETURN_CODE_HANDLE,
    SPECIAL_REGISTERS_LAYOUT,
)
from interpreter.instructions import AllocRegion, Const, LoadVar, StoreField
from interpreter.register import NO_REGISTER, Register
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)


def lower_data_division(
    ctx: EmitContext, layout: DataLayout, region: RegionId
) -> Register:
    """Emit ALLOC_REGION + initial VALUE encodings. Returns region register.

    ``region`` says which DATA DIVISION section this layout is, and is required:
    this one function initialises WORKING-STORAGE, LOCAL-STORAGE, FILE, INDEXES
    and SPECIAL-REGISTERS, so there is no defensible default. Extents in
    different regions never alias, so a wrong region here would silently erase
    every dependency edge on the fields it initialises.
    """
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const.int_(size_reg, layout.total_bytes))
    region_reg = ctx.fresh_reg()
    ctx.emit_inst(
        AllocRegion(result_reg=region_reg, size_reg=size_reg),
    )

    fields_with_values = [fl for fl in layout.all_leaves() if fl.value]
    for fl in fields_with_values:
        # A VALUE clause initialises the whole declared field at its own
        # offset — no subscript is in play — so the whole-field extent is
        # exactly right here.
        ctx.emit_field_encode(
            region_reg, fl, fl.value, extent=whole_field_extent(fl, region)
        )

    logger.debug(
        "Data Division: allocated %d bytes, initialized %d fields",
        layout.total_bytes,
        len(fields_with_values),
    )
    return region_reg


def lower_sectioned_data_division(
    ctx: EmitContext,
    layout: SectionedLayout,
    program_id: str,
) -> MaterialisedSectionedLayout:
    """Bind WS to the persistent singleton region; allocate fresh LS per call.

    The WS region handle must already be stored in __ws_region by the caller
    (currently the inline shim in CobolFrontend; Task 5 will replace this
    with the program init block that loads it from the singleton HeapObject).
    LINKAGE is bound to __params_region injected by _handle_call_with_memory.
    LOCAL-STORAGE is freshly allocated on every call.
    """
    ws_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=ws_reg, name=VarName("__ws_region")))

    if layout.linkage.total_bytes > 0:
        lk_reg = ctx.fresh_reg()
        ctx.emit_inst(LoadVar(result_reg=lk_reg, name=VarName("__params_region")))
    else:
        lk_reg = NO_REGISTER

    if layout.local_storage.total_bytes > 0:
        ls_reg = lower_data_division(ctx, layout.local_storage, RegionId.LOCAL_STORAGE)
    else:
        ls_reg = NO_REGISTER

    if layout.file.total_bytes > 0:
        file_reg = lower_data_division(ctx, layout.file, RegionId.FILE)
    else:
        file_reg = NO_REGISTER

    # INDEXED BY items belong to no record, so they get their own region rather
    # than being appended to one: LINKAGE in particular is the CALLER's argument
    # storage, sized by the caller and not by total_bytes, so an index placed
    # there would write past the arguments and corrupt them.
    if layout.indexes.total_bytes > 0:
        index_reg = lower_data_division(ctx, layout.indexes, RegionId.INDEXES)
    else:
        index_reg = NO_REGISTER

    # RETURN-CODE (and future special registers) live in a dedicated region,
    # allocated fresh per run and isolated from WS/LS/LINKAGE/FILE storage. Its
    # handle is published on the program singleton under RETURN_CODE_HANDLE so the
    # final value is recoverable from the returned VMState (see special_registers).
    sr_reg = lower_data_division(
        ctx, SPECIAL_REGISTERS_LAYOUT, RegionId.SPECIAL_REGISTERS
    )
    singleton_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadVar(result_reg=singleton_reg, name=VarName(f"__prog_{program_id.upper()}"))
    )
    ctx.emit_inst(
        StoreField(
            obj_reg=singleton_reg, field_name=RETURN_CODE_HANDLE, value_reg=sr_reg
        )
    )

    logger.debug(
        "Sectioned data division: WS=%s LK=%s LS=%s FILE=%s SR=%s IX=%s",
        ws_reg,
        lk_reg,
        ls_reg,
        file_reg,
        sr_reg,
        index_reg,
    )

    return MaterialisedSectionedLayout(
        working_storage=(layout.working_storage, ws_reg),
        linkage=(layout.linkage, lk_reg),
        local_storage=(layout.local_storage, ls_reg),
        file=(layout.file, file_reg),
        special_registers=(SPECIAL_REGISTERS_LAYOUT, sr_reg),
        indexes=(layout.indexes, index_reg),
    )
