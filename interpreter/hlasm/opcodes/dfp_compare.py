# pyright: standard
"""DFP COMPARE, COMPARE AND SIGNAL, COMPARE BIASED EXPONENT and LOAD AND TEST in IR on the decoded fields (rulings R44, R50; PoO 20-22, 20-23, 20-41, figures 20-12 to 20-15, 20-24): compare aligns both coefficients to the lower exponent and orders infinities ahead of them."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_slots import INVALID_BIT
from interpreter.hlasm.dfp_fields import INFINITY, QUIET_NAN, SIGNALING_NAN
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.opcodes.bfp_ir import emit_ieee_ladder
from interpreter.hlasm.opcodes.dfp_ir import (
    Fields,
    decoded,
    fields_of,
    set_fields_cc,
    store_fields,
)
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import FIRST, SECOND, compared, fpr, pick
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

UNORDERED_CC = 3
HIGH_CC = 2


def _operands(
    emitter: HlasmEmitter, statement: MachineStatement, layout: DfpLayout
) -> tuple[Fields, Fields]:
    first = decoded(fpr(FIRST, layout), layout)(emitter, statement)
    second = decoded(fpr(SECOND, layout), layout)(emitter, statement)
    return fields_of(emitter, first), fields_of(emitter, second)


type Signals = Callable[[HlasmEmitter, Register], Register]


def _op(
    emitter: HlasmEmitter, operator: BinopKind, left: Register, right: Register
) -> Register:
    return emitter.binop(operator, left, right)


def _signaling(emitter: HlasmEmitter, exponent: Register) -> Register:
    return compared(emitter, BinopKind.EQ, exponent, SIGNALING_NAN)


def _any_nan(emitter: HlasmEmitter, exponent: Register) -> Register:
    return compared(emitter, BinopKind.LE, exponent, QUIET_NAN)


def _signed_magnitude(
    emitter: HlasmEmitter, fields: Fields, finite: Register, floor: Register
) -> Register:
    sign, exponent, significand = fields
    scale = _op(
        emitter,
        BinopKind.POWER,
        emitter.int_(10),
        _op(
            emitter, BinopKind.SUB, _op(emitter, BinopKind.MUL, exponent, finite), floor
        ),
    )
    magnitude = _op(
        emitter, BinopKind.MUL, _op(emitter, BinopKind.MUL, significand, finite), scale
    )
    return _op(emitter, BinopKind.MUL, magnitude, _direction(emitter, sign))


def _direction(emitter: HlasmEmitter, sign: Register) -> Register:
    doubled = _op(emitter, BinopKind.MUL, sign, emitter.int_(2))
    return _op(emitter, BinopKind.SUB, emitter.int_(1), doubled)


def _orders(
    emitter: HlasmEmitter, a: Fields, b: Fields
) -> tuple[Register, Register, Register, Register]:
    finite_a, finite_b = (
        compared(emitter, BinopKind.GE, fields[1], 0) for fields in (a, b)
    )
    exponent_a = _op(emitter, BinopKind.MUL, a[1], finite_a)
    exponent_b = _op(emitter, BinopKind.MUL, b[1], finite_b)
    lower = _op(emitter, BinopKind.LT, exponent_a, exponent_b)
    floor = pick(emitter, lower, exponent_a, exponent_b)
    rank_a, rank_b = (
        _op(
            emitter,
            BinopKind.MUL,
            compared(emitter, BinopKind.EQ, fields[1], INFINITY),
            _direction(emitter, fields[0]),
        )
        for fields in (a, b)
    )
    return (
        rank_a,
        _signed_magnitude(emitter, a, finite_a, floor),
        rank_b,
        _signed_magnitude(emitter, b, finite_b, floor),
    )


def _before(
    emitter: HlasmEmitter, orders: tuple[Register, Register, Register, Register]
) -> Register:
    rank_a, value_a, rank_b, value_b = orders
    tied = _op(emitter, BinopKind.EQ, rank_a, rank_b)
    smaller = _op(emitter, BinopKind.LT, value_a, value_b)
    return _op(
        emitter,
        BinopKind.BIT_OR,
        _op(emitter, BinopKind.LT, rank_a, rank_b),
        _op(emitter, BinopKind.MUL, tied, smaller),
    )


def _compare_cc(emitter: HlasmEmitter, a: Fields, b: Fields) -> Register:
    rank_a, value_a, rank_b, value_b = _orders(emitter, a, b)
    low = _before(emitter, (rank_a, value_a, rank_b, value_b))
    high = _before(emitter, (rank_b, value_b, rank_a, value_a))
    order = _op(
        emitter,
        BinopKind.ADD,
        low,
        _op(emitter, BinopKind.MUL, high, emitter.int_(HIGH_CC)),
    )
    unordered = _op(
        emitter, BinopKind.BIT_OR, _any_nan(emitter, a[1]), _any_nan(emitter, b[1])
    )
    return pick(emitter, unordered, emitter.int_(UNORDERED_CC), order)


def _compare(signals: Signals, layout: DfpLayout) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        a, b = _operands(emitter, statement, layout)
        signaled = _op(
            emitter, BinopKind.BIT_OR, signals(emitter, a[1]), signals(emitter, b[1])
        )
        invalid = _op(emitter, BinopKind.MUL, signaled, emitter.int_(INVALID_BIT))
        cc = _compare_cc(emitter, a, b)
        none = emitter.int_(0)
        emit_ieee_ladder(
            emitter,
            IeeeOutcome(invalid, invalid, none, none),
            lambda slot: emitter.set_cc(cc),
        )

    return lower


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
        _compare(_signaling, LONG_DFP),
        _compare(_signaling, EXTENDED_DFP),
        ("CDTR", "CXTR"),
    ),
    **_forms(
        _compare(_any_nan, LONG_DFP),
        _compare(_any_nan, EXTENDED_DFP),
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
