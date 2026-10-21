# pyright: standard
"""Lowerings that splice a (result, CC) builder over register, storage or immediate operands and store both, with no trap."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import Sink, Source, storage_immediate
from interpreter.hlasm.hlasm_constants import PARAM_LEFT, PARAM_RIGHT
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_result_and_cc
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import InstructionBase
from interpreter.register import Register

type Operation = Sequence[InstructionBase]


def apply_result_and_cc(
    emitter: HlasmEmitter,
    operation: Operation,
    arguments: Mapping[Register, Register],
    store: Callable[[Register], None],
) -> None:
    result, cc = inline_result_and_cc(emitter, operation, arguments)
    store(result)
    emitter.set_cc(cc)


def result_and_cc(
    operation: Operation, operands: Sequence[tuple[Register, Source]], sink: Sink
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        arguments = {param: source(emitter, statement) for param, source in operands}
        apply_result_and_cc(
            emitter,
            operation,
            arguments,
            lambda value: sink(emitter, statement, value),
        )

    return lower


def storage_immediate_result_and_cc(
    operation: Operation, width: int
) -> StatementLowering:
    return storage_immediate(
        width,
        lambda emitter, operands, store: apply_result_and_cc(
            emitter,
            operation,
            {PARAM_LEFT: operands[0], PARAM_RIGHT: operands[1]},
            store,
        ),
    )
