# pyright: standard
"""DATA DIVISION lowering — allocate region and initialize field values."""

from __future__ import annotations

import logging

from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.instructions import AllocRegion, Const
from interpreter.register import Register

logger = logging.getLogger(__name__)


def lower_data_division(ctx: EmitContext, layout: DataLayout) -> str:
    """Emit ALLOC_REGION + initial VALUE encodings. Returns region register."""
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=size_reg, value=layout.total_bytes))  # type: ignore[arg-type]  # see red-dragon-0qgg
    region_reg = ctx.fresh_reg()
    ctx.emit_inst(
        AllocRegion(result_reg=region_reg, size_reg=size_reg),
    )

    fields_with_values = [fl for fl in layout.fields.values() if fl.value]
    for fl in fields_with_values:
        ctx.emit_field_encode(region_reg, fl, fl.value)  # type: ignore[arg-type]  # see red-dragon-pn3f

    logger.debug(
        "Data Division: allocated %d bytes, initialized %d fields",
        layout.total_bytes,
        len(fields_with_values),
    )
    return region_reg  # type: ignore[return-value]  # see red-dragon-pn3f
