# pyright: standard
"""HFP LOAD AND TEST, LOAD COMPLEMENT, LOAD NEGATIVE and LOAD POSITIVE in IR: a sign change on the image; extended results rebuild the low-order part, or a signed true zero for a zero fraction."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.hfp_layout import (
    EXTENDED_HFP,
    LONG_HFP,
    SHORT_HFP,
    HfpLayout,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import FIRST, SECOND, load_image, store_image
from interpreter.hlasm.opcodes.hfp_ir import (
    fields_of,
    image_cc,
    image_of,
    true_zero_low,
)
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type SignChange = Callable[[HlasmEmitter, Register], Register]

LAYOUTS: Mapping[str, HfpLayout] = {"E": SHORT_HFP, "D": LONG_HFP, "X": EXTENDED_HFP}


def _kept(emitter: HlasmEmitter, sign: Register) -> Register:
    return sign


def _complemented(emitter: HlasmEmitter, sign: Register) -> Register:
    return emitter.binop(BinopKind.BIT_XOR, sign, emitter.int_(1))


def _negative(emitter: HlasmEmitter, sign: Register) -> Register:
    return emitter.int_(1)


def _positive(emitter: HlasmEmitter, sign: Register) -> Register:
    return emitter.int_(0)


def _characteristic(
    emitter: HlasmEmitter,
    characteristic: Register,
    fraction: Register,
    layout: HfpLayout,
) -> Register:
    if layout is not EXTENDED_HFP:
        return characteristic
    nonzero = emitter.binop(BinopKind.NE, fraction, emitter.int_(0))
    return emitter.binop(BinopKind.MUL, nonzero, characteristic)


def _sign_form(change: SignChange, layout: HfpLayout) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        image = load_image(emitter, reg_operand(statement, SECOND), layout)
        sign, characteristic, fraction = fields_of(emitter, image, layout)
        fields = (
            change(emitter, sign),
            _characteristic(emitter, characteristic, fraction, layout),
            fraction,
        )
        result = image_of(emitter, fields, layout, true_zero_low)
        store_image(emitter, reg_operand(statement, FIRST), layout, result)
        emitter.set_cc(image_cc(emitter, result, layout))

    if layout is EXTENDED_HFP:
        return pairs((FIRST, SECOND), lower)
    return lower


HFP_SIGN_LOWERINGS: Mapping[str, StatementLowering] = {
    f"{prefix}{letter}R": _sign_form(change, layout)
    for prefix, change in (
        ("LT", _kept),
        ("LC", _complemented),
        ("LN", _negative),
        ("LP", _positive),
    )
    for letter, layout in LAYOUTS.items()
}
