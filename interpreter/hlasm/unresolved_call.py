# pyright: standard
"""Calls a program by the variable its name registers, with no arguments, as a static COBOL CALL to a missing program does."""

from interpreter.field_name import FieldName
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import CallWithMemory, NewArray, StoreField
from interpreter.register import Register
from interpreter.var_name import VarName

ARGUMENT_COUNT = FieldName("count")


def _no_arguments(emitter: HlasmEmitter) -> Register:
    arguments = emitter.fresh_reg()
    emitter.emit_inst(NewArray(result_reg=arguments, size_reg=emitter.int_(0)))
    emitter.emit_inst(
        StoreField(
            obj_reg=arguments, field_name=ARGUMENT_COUNT, value_reg=emitter.int_(0)
        )
    )
    return arguments


def emit_unresolved_call(
    emitter: HlasmEmitter, location: VarName | Register
) -> Register:
    result = emitter.fresh_reg()
    emitter.emit_inst(
        CallWithMemory(
            result_reg=result, location=location, memory=_no_arguments(emitter)
        )
    )
    return result
