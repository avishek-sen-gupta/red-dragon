"""DATA DIVISION lowering — allocate region and initialize field values."""

from __future__ import annotations

import logging

from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    SectionedLayout,
)
from interpreter.instructions import AllocRegion, Const, LoadVar
from interpreter.register import NO_REGISTER, Register
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)


def lower_data_division(ctx: EmitContext, layout: DataLayout) -> Register:
    """Emit ALLOC_REGION + initial VALUE encodings. Returns region register."""
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const.int_(size_reg, layout.total_bytes))
    region_reg = ctx.fresh_reg()
    ctx.emit_inst(
        AllocRegion(result_reg=region_reg, size_reg=size_reg),
    )

    fields_with_values = [fl for fl in layout.all_leaves() if fl.value]
    for fl in fields_with_values:
        ctx.emit_field_encode(region_reg, fl, fl.value)

    logger.debug(
        "Data Division: allocated %d bytes, initialized %d fields",
        layout.total_bytes,
        len(fields_with_values),
    )
    return region_reg


def lower_sectioned_data_division(
    ctx: EmitContext,
    layout: SectionedLayout,
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
        ls_reg = lower_data_division(ctx, layout.local_storage)
    else:
        ls_reg = NO_REGISTER

    if layout.file.total_bytes > 0:
        file_reg = lower_data_division(ctx, layout.file)
    else:
        file_reg = NO_REGISTER

    logger.debug(
        "Sectioned data division: WS=%s LK=%s LS=%s FILE=%s",
        ws_reg,
        lk_reg,
        ls_reg,
        file_reg,
    )

    return MaterialisedSectionedLayout(
        working_storage=(layout.working_storage, ws_reg),
        linkage=(layout.linkage, lk_reg),
        local_storage=(layout.local_storage, ls_reg),
        file=(layout.file, file_reg),
    )
