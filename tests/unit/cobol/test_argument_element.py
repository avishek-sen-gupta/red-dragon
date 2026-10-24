# pyright: standard
"""Each CALL argument element carries its argument mode and byte length beside its address."""

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_statements import CallStatement, CallTarget, CallUsingParam
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_call import lower_call
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import Const, NewObject, StoreField
from tests.covers import covers


def _field(name: str, pic: str, offset: int, usage: str = "DISPLAY") -> CobolField:
    return CobolField(name=name, level=1, pic=pic, usage=usage, offset=offset)


def _elements(ctx: EmitContext, start: int) -> list[dict[str, str | int | bool]]:
    emitted = ctx.instructions[start:]
    constants = {str(i.result_reg): i.value for i in emitted if isinstance(i, Const)}
    objects = [str(i.result_reg) for i in emitted if isinstance(i, NewObject)]

    def fields(obj: str) -> dict[str, str | int | bool]:
        return {
            str(i.field_name): constants.get(str(i.value_reg), "address")
            for i in emitted
            if isinstance(i, StoreField) and str(i.obj_reg) == obj
        }

    return [fields(obj) for obj in objects]


@covers(CobolFeature.CALL_USING)
def test_each_element_carries_mode_and_length() -> None:
    asg = CobolASG(
        data_fields=[
            _field("WS-A", "X(5)", 0),
            _field("WS-B", "X(3)", 5),
            _field("WS-N", "S9(9)", 8, "COMP-5"),
        ]
    )
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(
        ctx, build_sectioned_layout(asg), "TESTPGM"
    )
    statement = CallStatement(
        target=CallTarget.of_literal("ASMSUB"),
        using=[
            CallUsingParam(name="WS-A", param_type="REFERENCE"),
            CallUsingParam(name="WS-B", param_type="CONTENT"),
            CallUsingParam(name="WS-N", param_type="VALUE"),
            CallUsingParam(name="", omitted=True),
            CallUsingParam(name="7", param_type="VALUE", is_literal=True, numeric=True),
        ],
        giving=RefModOperand(name=""),
    )
    start = len(ctx.instructions)

    lower_call(ctx, statement, materialised)

    assert _elements(ctx, start) == [
        {
            "mode": "REFERENCE",
            "length": 5,
            "signed": False,
            "region": "address",
            "offset": 0,
        },
        {
            "mode": "CONTENT",
            "length": 3,
            "signed": False,
            "region": "address",
            "offset": 0,
        },
        {
            "mode": "VALUE",
            "length": 4,
            "signed": True,
            "region": "address",
            "offset": 0,
        },
        {"mode": "OMITTED", "length": 0},
        {
            "mode": "VALUE",
            "length": 4,
            "signed": True,
            "region": "address",
            "offset": 0,
        },
    ]
