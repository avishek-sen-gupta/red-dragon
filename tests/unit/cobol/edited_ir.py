"""Runs the numeric editing IR for one value and picture through the VM and returns the edited characters."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.numeric_edit_ir import emit_numeric_edit
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def edited(
    value: ParamValue, pic: str, currency: str = "$", scale: int = 0
) -> ParamValue:
    return edited_as(
        value,
        CobolTypeDescriptor(
            category=CobolDataCategory.NUMERIC_EDITED,
            total_digits=0,
            pic_string=pic,
            currency=currency,
            scale=scale,
        ),
    )


def edited_with_comma_point(value: ParamValue, pic: str) -> ParamValue:
    return edited_as(
        value,
        CobolTypeDescriptor(
            category=CobolDataCategory.NUMERIC_EDITED,
            total_digits=0,
            pic_string=pic,
            decimal_point_is_comma=True,
        ),
    )


def edited_as(value: ParamValue, td: CobolTypeDescriptor) -> ParamValue:
    return run_emitted(
        lambda e, registers: emit_numeric_edit(e, registers[0], td), (value,)
    )
