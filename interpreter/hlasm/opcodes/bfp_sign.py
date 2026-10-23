# pyright: standard
"""BFP LOAD AND TEST and the sign forms: IR on the image; only LOAD AND TEST signals, quieting an SNaN through the trap ladder."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_layout import (
    EXTENDED_LAYOUT,
    LONG_LAYOUT,
    SHORT_LAYOUT,
    BfpLayout,
)
from interpreter.hlasm.bfp_slots import INVALID_BIT
from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.opcodes.bfp_ir import (
    emit_ieee_ladder,
    image_cc,
    signaling_nan_of,
)
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import (
    load_image,
    store_image,
)
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type SignChange = Callable[[HlasmEmitter, Register, BfpLayout], Register]

TARGET, SOURCE = 0, 1
LAYOUTS: Mapping[str, BfpLayout] = {
    "E": SHORT_LAYOUT,
    "D": LONG_LAYOUT,
    "X": EXTENDED_LAYOUT,
}


def _store_with_cc(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    image: Register,
    layout: BfpLayout,
) -> None:
    store_image(emitter, reg_operand(statement, TARGET), layout, image)
    emitter.set_cc(image_cc(emitter, image, layout))


def _sign_bit(emitter: HlasmEmitter, layout: BfpLayout) -> Register:
    return emitter.int_(1 << layout.sign_shift)


def _complemented(
    emitter: HlasmEmitter, image: Register, layout: BfpLayout
) -> Register:
    return emitter.binop(BinopKind.BIT_XOR, image, _sign_bit(emitter, layout))


def _negative(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    return emitter.binop(BinopKind.BIT_OR, image, _sign_bit(emitter, layout))


def _positive(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    return keep(layout.magnitude_mask)(emitter, image)


def _sign_form(change: SignChange, layout: BfpLayout) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        image = load_image(emitter, reg_operand(statement, SOURCE), layout)
        _store_with_cc(emitter, statement, change(emitter, image, layout), layout)

    return lower


def _load_and_test(layout: BfpLayout) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        image = load_image(emitter, reg_operand(statement, SOURCE), layout)
        snan = signaling_nan_of(emitter, image, layout)
        quieting = emitter.binop(BinopKind.MUL, snan, emitter.int_(layout.quiet_bit))
        result = emitter.binop(BinopKind.BIT_OR, image, quieting)
        invalid = emitter.binop(BinopKind.MUL, snan, emitter.int_(INVALID_BIT))
        none = emitter.int_(0)
        emit_ieee_ladder(
            emitter,
            IeeeOutcome(invalid, invalid, none, none),
            lambda slot: _store_with_cc(emitter, statement, result, layout),
        )

    return lower


def _forms(
    prefix: str, lowering: Callable[[BfpLayout], StatementLowering]
) -> Mapping[str, StatementLowering]:
    return {
        f"{prefix}{letter}BR": (
            pairs((TARGET, SOURCE), lowering(layout))
            if layout is EXTENDED_LAYOUT
            else lowering(layout)
        )
        for letter, layout in LAYOUTS.items()
    }


BFP_SIGN_LOWERINGS: Mapping[str, StatementLowering] = {
    **_forms("LT", _load_and_test),
    **_forms("LC", lambda layout: _sign_form(_complemented, layout)),
    **_forms("LN", lambda layout: _sign_form(_negative, layout)),
    **_forms("LP", lambda layout: _sign_form(_positive, layout)),
}
