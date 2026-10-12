"""The COBOL run unit's own storage: one region the start-up module allocates before any program runs."""

from __future__ import annotations

from cobol_asg.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from interpreter.instructions import AllocRegion, Const, DeclVar, InstructionBase
from interpreter.register import Register
from interpreter.var_name import VarName

RUN_UNIT_VAR = VarName("__cobol_run_unit")
RUN_UNIT_RETURN_CODE = "RUN-UNIT-RETURN-CODE"
RANDOM_STATE = "RANDOM-STATE"

RUN_UNIT_LAYOUT = build_data_layout(
    [
        CobolField(
            name=RUN_UNIT_RETURN_CODE, level=1, pic="S9(4)", usage="COMP", offset=0
        ),
        CobolField(name=RANDOM_STATE, level=1, pic="X(4)", usage="DISPLAY", offset=2),
    ]
)


def run_unit_allocation() -> tuple[InstructionBase, ...]:
    size, region = Register("%0"), Register("%1")
    return (
        Const.int_(size, RUN_UNIT_LAYOUT.total_bytes),
        AllocRegion(result_reg=region, size_reg=size),
        DeclVar(name=RUN_UNIT_VAR, value_reg=region),
    )
