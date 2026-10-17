"""Numeric editing lowers to IR built from primitives, and a symbolic value flows through it."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.edited_ir import edited

_REMOVED = FuncName("__cobol_apply_edit_picture")


def _digit(index: int) -> str:
    return (
        "__string_slice('0123456789', __list_get("
        f"__cobol_prepare_digits(v, 2, 1, False, 0), {index}), 1)"
    )


@covers(CobolFeature.NUMERIC_EDITED)
def test_a_symbolic_value_flows_through_the_edited_image():
    image = edited(SymbolicValue("v"), "9.9")
    assert isinstance(image, SymbolicValue)
    assert image.constraints == [
        f"__string_concat_pair(__string_concat_pair({_digit(0)}, '.'), {_digit(1)})"
    ]


@covers(CobolFeature.NUMERIC_EDITED)
def test_an_edited_move_lowers_to_ir_without_the_edit_builtin():
    td = CobolTypeDescriptor(
        category=CobolDataCategory.NUMERIC_EDITED,
        total_digits=10,
        pic_string="$$,$$9.99CR",
    )
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    ctx.emit_encode_from_string(
        FieldLayout(name="AMOUNT", type_descriptor=td, offset=0, byte_length=10),
        ctx.const_to_reg("12.5"),
    )
    called = {
        str(inst.func_name)
        for inst in ctx.instructions
        if isinstance(inst, CallFunction)
    }
    assert called == {
        "__cobol_parse_number",
        "__cobol_prepare_digits",
        "__list_concat",
        "__list_get",
        "__list_slice",
        "__make_list",
        "__string_concat_pair",
        "__string_slice",
        "__string_to_bytes",
    }
    assert _REMOVED not in BYTE_BUILTINS
