# pyright: standard
"""Statement-level BFP lowering parts: operand sources, the rounding modifier, M-field checks, image stores after delivery, and a BFP builtin call through the shared trap ladder."""

from collections.abc import Callable, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_layout import BfpLayout
from interpreter.hlasm.bfp_operation import BfpOperation, bfp_builtin_name
from interpreter.hlasm.data_movement import Source
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_ir import (
    current_mode,
    fields_list,
    image_at,
    image_cc,
)
from interpreter.hlasm.opcodes.fp_forms import (
    Deliver,
    SuppressedBits,
    ieee_call,
    signals_all,
)
from interpreter.hlasm.opcodes.fpr_images import store_image
from interpreter.hlasm.operands import mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.register import Register

type AfterStore = Callable[[HlasmEmitter, Register], None]

VALID_MODIFIERS = frozenset({0, 1, 3, 4, 5, 6, 7})


def fields(image: Source, layout: BfpLayout) -> Source:
    return lambda emitter, statement: fields_list(
        emitter, image(emitter, statement), layout
    )


def current(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return current_mode(emitter)


def modifier(index: int) -> Source:
    def mode(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
        code = mask_operand(statement, index)
        if code == 0:
            return current_mode(emitter)
        return emitter.int_(code)

    return mode


def no_cc(emitter: HlasmEmitter, image: Register) -> None:
    return None


def cc_of(layout: BfpLayout) -> AfterStore:
    return lambda emitter, image: emitter.set_cc(image_cc(emitter, image, layout))


def stored(index: int, layout: BfpLayout, after: AfterStore) -> Deliver:
    def deliver(
        emitter: HlasmEmitter,
        statement: MachineStatement,
        result: Register,
        slot: Register,
    ) -> None:
        image = image_at(emitter, result, slot, layout)
        store_image(emitter, reg_operand(statement, index), layout, image)
        after(emitter, image)

    return deliver


def ieee(
    builtin: tuple[BfpOperation, BfpLayout],
    arguments: Sequence[Source],
    deliver: Deliver,
    suppressed: SuppressedBits = signals_all,
) -> StatementLowering:
    return ieee_call(bfp_builtin_name(*builtin), arguments, deliver, suppressed)


def invalid_modifier(index: int) -> Callable[[MachineStatement], bool]:
    return lambda statement: mask_operand(statement, index) not in VALID_MODIFIERS
