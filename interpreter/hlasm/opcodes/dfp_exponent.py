# pyright: standard
"""DFP EXTRACT BIASED EXPONENT, EXTRACT SIGNIFICANCE and INSERT BIASED EXPONENT in IR on the decoded fields (ruling R44, PoO 20-39, 20-40, figures 20-21 to 20-23)."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import from_gr64
from interpreter.hlasm.dfp_fields import INFINITY, QUIET_NAN, SIGNALING_NAN
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.dfp_ir import decoded, fields_of, store_fields
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import FIRST, SECOND, THIRD, fpr, pick
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

SIGN_BIT = 1 << 63
GR_MODULUS = 1 << 64


type Extracted = Callable[[HlasmEmitter, Register, Register, DfpLayout], Register]


def _sum(emitter: HlasmEmitter, values: Sequence[Register]) -> Register:
    first, *rest = values
    return emitter.binop(BinopKind.ADD, first, _sum(emitter, rest)) if rest else first


def _significance(
    emitter: HlasmEmitter, exponent: Register, significand: Register, layout: DfpLayout
) -> Register:
    reached = [
        emitter.binop(BinopKind.GE, significand, emitter.int_(10**k))
        for k in range(layout.format.precision)
    ]
    finite = emitter.binop(BinopKind.GE, exponent, emitter.int_(0))
    return pick(emitter, finite, _sum(emitter, reached), exponent)


def _exponent(
    emitter: HlasmEmitter, exponent: Register, significand: Register, layout: DfpLayout
) -> Register:
    return exponent


def _extract(layout: DfpLayout, extracted: Extracted) -> StatementLowering:
    source = decoded(fpr(SECOND, layout), layout)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        _, exponent, significand = fields_of(emitter, source(emitter, statement))
        value = extracted(emitter, exponent, significand, layout)
        emitter.store_gr64(reg_operand(statement, FIRST), value)

    return lower


def _signed(emitter: HlasmEmitter, value: Register) -> Register:
    negative = emitter.binop(BinopKind.GE, value, emitter.int_(SIGN_BIT))
    wrap = emitter.binop(BinopKind.MUL, negative, emitter.int_(GR_MODULUS))
    return emitter.binop(BinopKind.SUB, value, wrap)


def _requested(emitter: HlasmEmitter, value: Register, layout: DfpLayout) -> Register:
    within = emitter.binop(
        BinopKind.MUL,
        emitter.binop(BinopKind.GE, value, emitter.int_(0)),
        emitter.binop(BinopKind.LE, value, emitter.int_(layout.max_biased_exponent)),
    )
    special = emitter.binop(
        BinopKind.BIT_OR,
        emitter.binop(BinopKind.EQ, value, emitter.int_(INFINITY)),
        emitter.binop(BinopKind.EQ, value, emitter.int_(SIGNALING_NAN)),
    )
    kept = emitter.binop(BinopKind.BIT_OR, within, special)
    return pick(emitter, kept, value, emitter.int_(QUIET_NAN))


def _insert(layout: DfpLayout) -> StatementLowering:
    source = decoded(fpr(SECOND, layout), layout)
    exponent = from_gr64(THIRD)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        requested = _requested(
            emitter, _signed(emitter, exponent(emitter, statement)), layout
        )
        sign, _, significand = fields_of(emitter, source(emitter, statement))
        fields = (sign, requested, significand)
        store_fields(emitter, reg_operand(statement, FIRST), layout, fields)

    return lower


DFP_EXPONENT_LOWERINGS: Mapping[str, StatementLowering] = {
    "EEDTR": _extract(LONG_DFP, _exponent),
    "EEXTR": pairs((SECOND,), _extract(EXTENDED_DFP, _exponent)),
    "ESDTR": _extract(LONG_DFP, _significance),
    "ESXTR": pairs((SECOND,), _extract(EXTENDED_DFP, _significance)),
    "IEDTR": _insert(LONG_DFP),
    "IEXTR": pairs((FIRST, SECOND), _insert(EXTENDED_DFP)),
}
