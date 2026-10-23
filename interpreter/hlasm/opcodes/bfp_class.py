# pyright: standard
"""BFP COMPARE, COMPARE AND SIGNAL and TEST DATA CLASS in IR on the operand images (ruling R44): NaN and class checks, then a sign-magnitude order."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_layout import (
    EXTENDED_LAYOUT,
    LONG_LAYOUT,
    SHORT_LAYOUT,
    BfpLayout,
)
from interpreter.hlasm.data_movement import (
    Source,
    keep,
    storage_address_at,
)
from interpreter.hlasm.fp_slots import INVALID_BIT
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.opcodes.bfp_ir import (
    magnitude_of,
    nan_of,
    quiet_of,
    signaling_nan_of,
)
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fp_ir import emit_ieee_ladder
from interpreter.hlasm.opcodes.fpr_images import (
    FIRST,
    SECOND,
    compared,
    fpr,
    pick,
    storage,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Signals = Callable[[HlasmEmitter, Register, BfpLayout], Register]

UNORDERED_CC = 3
HIGH_CC = 2
DATA_CLASS_BITS = 0xFFF
LAST_CLASS_BIT = 11
SUBNORMAL_CLASS = 2
INFINITY_CLASS = 3
SIGNALING_CLASS = 5


def _times(emitter: HlasmEmitter, value: Register, factor: int) -> Register:
    return emitter.binop(BinopKind.MUL, value, emitter.int_(factor))


def _sign(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    return emitter.binop(BinopKind.RSHIFT, image, emitter.int_(layout.sign_shift))


def _signed_magnitude(
    emitter: HlasmEmitter, image: Register, layout: BfpLayout
) -> Register:
    direction = emitter.binop(
        BinopKind.SUB,
        emitter.int_(1),
        _times(emitter, _sign(emitter, image, layout), 2),
    )
    return emitter.binop(BinopKind.MUL, magnitude_of(emitter, image, layout), direction)


def _ordered_cc(
    emitter: HlasmEmitter, a: Register, b: Register, layout: BfpLayout
) -> Register:
    left, right = _signed_magnitude(emitter, a, layout), _signed_magnitude(
        emitter, b, layout
    )
    low = emitter.binop(BinopKind.LT, left, right)
    high = emitter.binop(BinopKind.GT, left, right)
    return emitter.binop(BinopKind.ADD, low, _times(emitter, high, HIGH_CC))


def _either(
    emitter: HlasmEmitter, test: Signals, a: Register, b: Register, layout: BfpLayout
) -> Register:
    return emitter.binop(
        BinopKind.BIT_OR, test(emitter, a, layout), test(emitter, b, layout)
    )


def _compare_cc(
    emitter: HlasmEmitter, a: Register, b: Register, layout: BfpLayout
) -> Register:
    ordered = _ordered_cc(emitter, a, b, layout)
    unordered = _either(emitter, nan_of, a, b, layout)
    return pick(emitter, unordered, emitter.int_(UNORDERED_CC), ordered)


def _compare(signals: Signals, layout: BfpLayout, second: Source) -> StatementLowering:
    first = fpr(FIRST, layout)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        a, b = first(emitter, statement), second(emitter, statement)
        invalid = _times(emitter, _either(emitter, signals, a, b, layout), INVALID_BIT)
        cc = _compare_cc(emitter, a, b, layout)
        none = emitter.int_(0)
        emit_ieee_ladder(
            emitter,
            IeeeOutcome(invalid, invalid, none, none),
            lambda slot: emitter.set_cc(cc),
        )

    return lower


def _compare_forms(
    signals: Signals, names: tuple[str, str, str, str, str]
) -> Mapping[str, StatementLowering]:
    short, long, extended, short_storage, long_storage = names
    return {
        short: _compare(signals, SHORT_LAYOUT, fpr(SECOND, SHORT_LAYOUT)),
        long: _compare(signals, LONG_LAYOUT, fpr(SECOND, LONG_LAYOUT)),
        extended: pairs(
            (FIRST, SECOND),
            _compare(signals, EXTENDED_LAYOUT, fpr(SECOND, EXTENDED_LAYOUT)),
        ),
        short_storage: _compare(signals, SHORT_LAYOUT, storage(SECOND, SHORT_LAYOUT)),
        long_storage: _compare(signals, LONG_LAYOUT, storage(SECOND, LONG_LAYOUT)),
    }


def _data_class(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    magnitude = magnitude_of(emitter, image, layout)
    smallest = 1 << layout.fraction_bits
    nonzero = compared(emitter, BinopKind.NE, magnitude, 0)
    below = compared(emitter, BinopKind.LT, magnitude, smallest)
    finite = compared(emitter, BinopKind.LT, magnitude, layout.infinity)
    normal = emitter.binop(
        BinopKind.MUL,
        compared(emitter, BinopKind.GE, magnitude, smallest),
        finite,
    )
    subnormal = emitter.binop(BinopKind.MUL, nonzero, below)
    infinite = compared(emitter, BinopKind.EQ, magnitude, layout.infinity)
    nan_class = emitter.binop(
        BinopKind.SUB, emitter.int_(SIGNALING_CLASS), quiet_of(emitter, image, layout)
    )
    classes = (
        normal,
        _times(emitter, subnormal, SUBNORMAL_CLASS),
        _times(emitter, infinite, INFINITY_CLASS),
        emitter.binop(BinopKind.MUL, nan_of(emitter, image, layout), nan_class),
    )
    return emitter.binop(
        BinopKind.ADD,
        emitter.binop(BinopKind.ADD, classes[0], classes[1]),
        emitter.binop(BinopKind.ADD, classes[2], classes[3]),
    )


def _test_data_class(layout: BfpLayout) -> StatementLowering:
    operand = fpr(FIRST, layout)
    address = storage_address_at(SECOND)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        image = operand(emitter, statement)
        mask = keep(DATA_CLASS_BITS)(emitter, address(emitter, statement))
        selector = emitter.binop(
            BinopKind.ADD,
            _times(emitter, _data_class(emitter, image, layout), 2),
            _sign(emitter, image, layout),
        )
        shift = emitter.binop(BinopKind.SUB, emitter.int_(LAST_CLASS_BIT), selector)
        selected = emitter.binop(BinopKind.RSHIFT, mask, shift)
        emitter.set_cc(keep(1)(emitter, selected))

    return lower


BFP_CLASS_LOWERINGS: Mapping[str, StatementLowering] = {
    **_compare_forms(signaling_nan_of, ("CEBR", "CDBR", "CXBR", "CEB", "CDB")),
    **_compare_forms(nan_of, ("KEBR", "KDBR", "KXBR", "KEB", "KDB")),
    "TCEB": _test_data_class(SHORT_LAYOUT),
    "TCDB": _test_data_class(LONG_LAYOUT),
    "TCXB": pairs((FIRST,), _test_data_class(EXTENDED_LAYOUT)),
}
