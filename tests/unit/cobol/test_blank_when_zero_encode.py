"""BLANK WHEN ZERO guards a MOVE into a numeric-edited item, never a VALUE."""

from __future__ import annotations

from cobol_asg.pic_parser import parse_pic
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import CallFunction
from tests.covers import covers


def _field(pic: str, value: str, *, value_is_numeric: bool) -> FieldLayout:
    td = parse_pic(pic, blank_when_zero=True)
    return FieldLayout(
        name="F",
        type_descriptor=td,
        offset=0,
        byte_length=td.byte_length,
        value=value,
        value_is_numeric=value_is_numeric,
    )


def _edit_calls(ctx: EmitContext) -> list[str]:
    edit_builtins = {
        BuiltinName.COBOL_PREPARE_DIGITS,
        BuiltinName.COBOL_BLANK_WHEN_ZERO,
    }
    return [
        str(inst.func_name)
        for inst in ctx.instructions
        if isinstance(inst, CallFunction) and str(inst.func_name) in edit_builtins
    ]


@covers(CobolFeature.BLANK_WHEN_ZERO, CobolFeature.NUMERIC_EDITED)
def test_blank_when_zero_wraps_the_edited_move_and_skips_the_value() -> None:
    move_ctx = EmitContext(dispatch_fn=dispatch_statement)
    edited = _field("$9999", "", value_is_numeric=False)
    move_ctx.emit_encode_from_string(edited, move_ctx.const_to_reg(0))
    edited_value_ctx = EmitContext(dispatch_fn=dispatch_statement)
    edited_value_ctx.emit_encode_value(_field("ZZ9", "0", value_is_numeric=True), "0")
    assert (_edit_calls(move_ctx), _edit_calls(edited_value_ctx)) == (
        [BuiltinName.COBOL_PREPARE_DIGITS, BuiltinName.COBOL_BLANK_WHEN_ZERO],
        [BuiltinName.COBOL_PREPARE_DIGITS],
    )
