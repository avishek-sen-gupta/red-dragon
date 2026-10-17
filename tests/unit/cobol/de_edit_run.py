"""Runs the de-editing IR for one PICTURE over an image, through the VM."""

from cobol_asg.edit_picture import de_edit_plan
from interpreter.cobol.de_edit_ir import emit_de_edit
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import Register
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def de_edit(
    image: ParamValue,
    pic: str,
    currency: str = "$",
    decimal_point_is_comma: bool = False,
) -> ParamValue:
    plan = de_edit_plan(pic, currency, decimal_point_is_comma)

    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        return emit_de_edit(e, registers[0], plan)

    return run_emitted(emit, (image,))
