# pyright: standard
"""Statement-level lowering parts the IEEE radixes share: one builtin call through the trap ladder (ruling R43), the suppressed-bit choices, specification checks, and the general-register and rounded-image stores after delivery."""

from collections.abc import Callable, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.func_name import FuncName
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.conditional import pick
from interpreter.hlasm.data_movement import Source, keep
from interpreter.hlasm.fp_slots import CC_SLOT, INEXACT_BIT
from interpreter.hlasm.fpr_layout import FprLayout
from interpreter.hlasm.hlasm_constants import SPECIFICATION_EXCEPTION_ABEND
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.fp_ir import (
    OutcomeStep,
    as_raised,
    emit_ieee_ladder,
    outcome_of,
    without,
)
from interpreter.hlasm.opcodes.fpr_images import (
    FIRST,
    FOURTH,
    list_item,
    load_image,
    store_image,
)
from interpreter.hlasm.operands import optional_mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Deliver = Callable[[HlasmEmitter, MachineStatement, Register, Register], None]
type SuppressedBits = Callable[[MachineStatement], int]
type GrStore = Callable[[HlasmEmitter, int, Register], None]
type ImageAt[L: FprLayout] = Callable[[HlasmEmitter, Register, Register, L], Register]

INEXACT_CONTROL = 0b0100


def result_cc(
    emitter: HlasmEmitter, statement: MachineStatement, result: Register, slot: Register
) -> None:
    emitter.set_cc(list_item(emitter, result, CC_SLOT))


def signals_all(statement: MachineStatement) -> int:
    return 0


def inexact_control(statement: MachineStatement) -> int:
    controlled = optional_mask_operand(statement, FOURTH, 0) & INEXACT_CONTROL
    return INEXACT_BIT * bool(controlled)


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


def integer_stored(store: GrStore) -> Deliver:
    def deliver(
        emitter: HlasmEmitter,
        statement: MachineStatement,
        result: Register,
        slot: Register,
    ) -> None:
        store(emitter, reg_operand(statement, FIRST), list_item(emitter, result, 0))
        emitter.set_cc(list_item(emitter, result, CC_SLOT))

    return deliver


def rounded_stored[L: FprLayout](source: L, target: L, image: ImageAt[L]) -> Deliver:
    narrowing = source.width - target.width

    def deliver(
        emitter: HlasmEmitter,
        statement: MachineStatement,
        result: Register,
        slot: Register,
    ) -> None:
        r1 = reg_operand(statement, FIRST)
        rounded = image(emitter, result, slot, target)
        scaled = image(emitter, result, slot, source)
        kept = keep((1 << narrowing) - 1)(emitter, load_image(emitter, r1, source))
        placed = emitter.binop(BinopKind.LSHIFT, rounded, emitter.int_(narrowing))
        merged = emitter.binop(BinopKind.BIT_OR, placed, kept)
        trapped = emitter.binop(BinopKind.NE, slot, emitter.int_(0))
        store_image(emitter, r1, source, pick(emitter, trapped, scaled, merged))

    return deliver
