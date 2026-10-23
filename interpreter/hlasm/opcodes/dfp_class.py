# pyright: standard
"""DFP TEST DATA CLASS and TEST DATA GROUP in IR on the decoded fields (ruling R44, PoO 20-56 to 20-58, figures 20-30, 20-31): the class or group and the sign select one of the address's twelve low bits."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.conditional import pick
from interpreter.hlasm.data_movement import keep, storage_address_at
from interpreter.hlasm.dfp_layout import (
    EXTENDED_DFP,
    LONG_DFP,
    SHORT_DFP,
    DfpLayout,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.dfp_ir import Fields, decoded, fields_of
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import FIRST, SECOND, compared, fpr
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Selector = Callable[[HlasmEmitter, Fields, DfpLayout], Register]

SELECTION_BITS = 0xFFF
LAST_BIT = 11
NORMAL_CLASS = 2
NAN_CLASS_BASE = 2
SPECIAL_GROUP = 5
SAFE_NONZERO_GROUP = 3
EXTREME_NONZERO_GROUP = 2


def _subnormal(emitter: HlasmEmitter, fields: Fields, layout: DfpLayout) -> Register:
    _, exponent, significand = fields
    below = emitter.binop(
        BinopKind.SUB, emitter.int_(layout.bias + layout.format.emin), exponent
    )
    places = emitter.binop(
        BinopKind.MUL, below, compared(emitter, BinopKind.GT, below, 0)
    )
    threshold = emitter.binop(BinopKind.POWER, emitter.int_(10), places)
    return emitter.binop(BinopKind.LT, significand, threshold)


def _data_class(emitter: HlasmEmitter, fields: Fields, layout: DfpLayout) -> Register:
    _, exponent, significand = fields
    nonzero = compared(emitter, BinopKind.NE, significand, 0)
    normal_or_not = emitter.binop(
        BinopKind.SUB,
        emitter.int_(NORMAL_CLASS),
        _subnormal(emitter, fields, layout),
    )
    finite_class = emitter.binop(BinopKind.MUL, nonzero, normal_or_not)
    special_class = emitter.binop(BinopKind.SUB, emitter.int_(NAN_CLASS_BASE), exponent)
    finite = compared(emitter, BinopKind.GE, exponent, 0)
    return pick(emitter, finite, finite_class, special_class)


def _data_group(emitter: HlasmEmitter, fields: Fields, layout: DfpLayout) -> Register:
    _, exponent, significand = fields
    extreme = emitter.binop(
        BinopKind.BIT_OR,
        compared(emitter, BinopKind.EQ, exponent, 0),
        compared(emitter, BinopKind.EQ, exponent, layout.max_biased_exponent),
    )
    leftmost = compared(emitter, BinopKind.GE, significand, 10**layout.trailing_digits)
    safe = emitter.binop(BinopKind.ADD, emitter.int_(SAFE_NONZERO_GROUP), leftmost)
    nonzero_group = pick(emitter, extreme, emitter.int_(EXTREME_NONZERO_GROUP), safe)
    nonzero = compared(emitter, BinopKind.NE, significand, 0)
    finite_group = pick(emitter, nonzero, nonzero_group, extreme)
    finite = compared(emitter, BinopKind.GE, exponent, 0)
    return pick(emitter, finite, finite_group, emitter.int_(SPECIAL_GROUP))


def _test(layout: DfpLayout, selector: Selector) -> StatementLowering:
    source = decoded(fpr(FIRST, layout), layout)
    address = storage_address_at(SECOND)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        mask = keep(SELECTION_BITS)(emitter, address(emitter, statement))
        fields = fields_of(emitter, source(emitter, statement))
        chosen = emitter.binop(
            BinopKind.ADD,
            emitter.binop(
                BinopKind.MUL, selector(emitter, fields, layout), emitter.int_(2)
            ),
            fields[0],
        )
        shift = emitter.binop(BinopKind.SUB, emitter.int_(LAST_BIT), chosen)
        selected = emitter.binop(BinopKind.RSHIFT, mask, shift)
        emitter.set_cc(keep(1)(emitter, selected))

    return lower


DFP_CLASS_LOWERINGS: Mapping[str, StatementLowering] = {
    "TDCET": _test(SHORT_DFP, _data_class),
    "TDCDT": _test(LONG_DFP, _data_class),
    "TDCXT": pairs((FIRST,), _test(EXTENDED_DFP, _data_class)),
    "TDGET": _test(SHORT_DFP, _data_group),
    "TDGDT": _test(LONG_DFP, _data_group),
    "TDGXT": pairs((FIRST,), _test(EXTENDED_DFP, _data_group)),
}
