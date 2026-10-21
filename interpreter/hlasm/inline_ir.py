# pyright: standard
"""Splices a fixed-width IR builder's body into the lowering under fresh registers."""

from collections.abc import Mapping, Sequence

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.hlasm_lowering_error import HlasmLoweringError
from interpreter.instructions import InstructionBase, Return_
from interpreter.register import Register


def _returned_register(body: Sequence[InstructionBase]) -> Register:
    match body[-1:]:
        case [Return_(value_reg=Register() as value)]:
            return value
        case last:
            raise HlasmLoweringError(
                "inline IR body",
                "a final Return_ of a register",
                repr(last[0]) if last else "an empty body",
            )


def inline_ir(
    emitter: HlasmEmitter,
    body: Sequence[InstructionBase],
    arguments: Mapping[Register, Register],
) -> Register:
    steps = body[:-1]
    value = _returned_register(body)
    renamed = {
        **arguments,
        **{
            step.result_reg: emitter.fresh_reg()
            for step in steps
            if step.result_reg.is_present()
        },
    }
    _ = [
        emitter.emit_inst(step.map_registers(lambda r: renamed.get(r, r)))
        for step in steps
    ]
    return renamed[value]
