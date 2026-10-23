# pyright: standard
"""Statement-level BFP lowering parts: operand sources, the rounding modifier, M-field checks, stores after delivery, and one builtin call through the trap ladder (ruling R43)."""

from collections.abc import Callable, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.func_name import FuncName
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.bfp_layout import BfpLayout
from interpreter.hlasm.bfp_operation import BfpOperation, bfp_builtin_name
from interpreter.hlasm.bfp_slots import CC_SLOT, INEXACT_BIT
from interpreter.hlasm.data_movement import Source
from interpreter.hlasm.hlasm_constants import (
    SPECIFICATION_EXCEPTION_ABEND,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_ir import (
    OutcomeStep,
    as_raised,
    current_mode,
    emit_ieee_ladder,
    fields_list,
    image_at,
    image_cc,
    outcome_of,
    without,
)
from interpreter.hlasm.opcodes.fpr_images import FOURTH, list_item, store_image
from interpreter.hlasm.operands import mask_operand, optional_mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.register import Register

type Deliver = Callable[[HlasmEmitter, MachineStatement, Register, Register], None]
type AfterStore = Callable[[HlasmEmitter, Register], None]
type SuppressedBits = Callable[[MachineStatement], int]

VALID_MODIFIERS = frozenset({0, 1, 3, 4, 5, 6, 7})
INEXACT_CONTROL = 0b0100


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


def result_cc(
    emitter: HlasmEmitter, statement: MachineStatement, result: Register, slot: Register
) -> None:
    emitter.set_cc(list_item(emitter, result, CC_SLOT))


def signals_all(statement: MachineStatement) -> int:
    return 0


def inexact_control(statement: MachineStatement) -> int:
    controlled = optional_mask_operand(statement, FOURTH, 0) & INEXACT_CONTROL
    return INEXACT_BIT * bool(controlled)


def ieee(
    builtin: tuple[BfpOperation, BfpLayout],
    arguments: Sequence[Source],
    deliver: Deliver,
    suppressed: SuppressedBits = signals_all,
) -> StatementLowering:
    return ieee_call(bfp_builtin_name(*builtin), arguments, deliver, suppressed)


def ieee_call(
    name: FuncName,
    arguments: Sequence[Source],
    deliver: Deliver,
    suppressed: SuppressedBits,
    step: OutcomeStep = as_raised,
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        args = tuple(argument(emitter, statement) for argument in arguments)
        result = emitter.call(name, args)
        outcome = without(emitter, outcome_of(emitter, result), suppressed(statement))
        emit_ieee_ladder(
            emitter,
            outcome,
            lambda slot: deliver(emitter, statement, result, slot),
            step,
        )

    return lower


def checked(
    raised: Callable[[MachineStatement], bool], lowering: StatementLowering
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        if raised(statement):
            emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
            return
        lowering(emitter, statement)

    return lower


def invalid_modifier(index: int) -> Callable[[MachineStatement], bool]:
    return lambda statement: mask_operand(statement, index) not in VALID_MODIFIERS
