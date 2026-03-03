"""DATA DIVISION lowering — allocate region and initialize field values."""

from __future__ import annotations

import logging

from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.ir import Opcode

logger = logging.getLogger(__name__)


def lower_data_division(ctx: EmitContext, layout: DataLayout) -> str:
    """Emit ALLOC_REGION + initial VALUE encodings. Returns region register."""
    region_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.ALLOC_REGION,
        result_reg=region_reg,
        operands=[layout.total_bytes],
    )

    fields_with_values = [fl for fl in layout.fields.values() if fl.value]
    for fl in fields_with_values:
        ctx.emit_field_encode(region_reg, fl, fl.value)

    logger.debug(
        "Data Division: allocated %d bytes, initialized %d fields",
        layout.total_bytes,
        len(fields_with_values),
    )
    return region_reg
