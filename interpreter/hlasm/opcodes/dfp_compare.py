# pyright: standard
"""DFP COMPARE and COMPARE AND SIGNAL through a builtin; COMPARE BIASED EXPONENT and LOAD AND TEST in IR on the decoded fields (ruling R44, PoO 20-22, 20-23, 20-41, figures 20-15, 20-24)."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_slots import INVALID_BIT
from interpreter.hlasm.dfp_fields import INFINITY, SIGNALING_NAN
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.dfp_operation import DfpOperation, dfp_builtin_name
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.opcodes.bfp_forms import ieee_call, result_cc, signals_all
from interpreter.hlasm.opcodes.bfp_ir import emit_ieee_ladder
from interpreter.hlasm.opcodes.dfp_ir import (
    Fields,
    decoded,
    fields_of,
    set_fields_cc,
    store_fields,
)
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import FIRST, SECOND, fpr, pick
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

UNORDERED_CC = 3
HIGH_CC = 2


def _compare(operation: DfpOperation, layout: DfpLayout) -> StatementLowering:
    return ieee_call(
        dfp_builtin_name(operation, layout),
        (decoded(fpr(FIRST, layout), layout), decoded(fpr(SECOND, layout), layout)),
        result_cc,
        signals_all,
    )


def _operands(
    emitter: HlasmEmitter, statement: MachineStatement, layout: DfpLayout
) -> tuple[Fields, Fields]:
    first = decoded(fpr(FIRST, layout), layout)(emitter, statement)
    second = decoded(fpr(SECOND, layout), layout)(emitter, statement)
    return fields_of(emitter, first), fields_of(emitter, second)


def _kind(emitter: HlasmEmitter, exponent: Register) -> Register:
    special = emitter.binop(BinopKind.LT, exponent, emitter.int_(0))
    nan = emitter.binop(BinopKind.LT, exponent, emitter.int_(INFINITY))
    return emitter.binop(BinopKind.ADD, special, nan)


def _exponent_cc(emitter: HlasmEmitter, a: Register, b: Register) -> Register:
    kind = _kind(emitter, a)
    same = emitter.binop(BinopKind.EQ, kind, _kind(emitter, b))
    low = emitter.binop(BinopKind.LT, a, b)
    high = emitter.binop(BinopKind.GT, a, b)
    order = emitter.binop(
        BinopKind.ADD, low, emitter.binop(BinopKind.MUL, high, emitter.int_(HIGH_CC))
    )
    finite = emitter.binop(BinopKind.EQ, kind, emitter.int_(0))
    ordered = emitter.binop(BinopKind.MUL, finite, order)
    return pick(emitter, same, ordered, emitter.int_(UNORDERED_CC))


def _compare_exponents(layout: DfpLayout) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        first, second = _operands(emitter, statement, layout)
        emitter.set_cc(_exponent_cc(emitter, first[1], second[1]))

    return lower


def _tested(emitter: HlasmEmitter, fields: Fields) -> tuple[Fields, Register]:
    sign, exponent, significand = fields
    signaling = emitter.binop(BinopKind.EQ, exponent, emitter.int_(SIGNALING_NAN))
    quieted = emitter.binop(BinopKind.ADD, exponent, signaling)
    finite_or_nan = emitter.binop(BinopKind.NE, exponent, emitter.int_(INFINITY))
    kept = emitter.binop(BinopKind.MUL, significand, finite_or_nan)
    invalid = emitter.binop(BinopKind.MUL, signaling, emitter.int_(INVALID_BIT))
    return (sign, quieted, kept), invalid


def _load_and_test(layout: DfpLayout) -> StatementLowering:
    source = decoded(fpr(SECOND, layout), layout)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        fields, invalid = _tested(
            emitter, fields_of(emitter, source(emitter, statement))
        )
        none = emitter.int_(0)

        def deliver(slot: Register) -> None:
            store_fields(emitter, reg_operand(statement, FIRST), layout, fields)
            set_fields_cc(emitter, fields)

        emit_ieee_ladder(emitter, IeeeOutcome(invalid, invalid, none, none), deliver)

    return lower


def _forms(
    long: StatementLowering, extended: StatementLowering, names: tuple[str, str]
) -> Mapping[str, StatementLowering]:
    return {names[0]: long, names[1]: pairs((FIRST, SECOND), extended)}


DFP_COMPARE_LOWERINGS: Mapping[str, StatementLowering] = {
    **_forms(
        _compare(DfpOperation.COMPARE, LONG_DFP),
        _compare(DfpOperation.COMPARE, EXTENDED_DFP),
        ("CDTR", "CXTR"),
    ),
    **_forms(
        _compare(DfpOperation.COMPARE_SIGNALING, LONG_DFP),
        _compare(DfpOperation.COMPARE_SIGNALING, EXTENDED_DFP),
        ("KDTR", "KXTR"),
    ),
    **_forms(
        _compare_exponents(LONG_DFP),
        _compare_exponents(EXTENDED_DFP),
        ("CEDTR", "CEXTR"),
    ),
    **_forms(
        _load_and_test(LONG_DFP), _load_and_test(EXTENDED_DFP), ("LTDTR", "LTXTR")
    ),
}
