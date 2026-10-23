# pyright: standard
"""DFP conversions to and from fixed point and between DFP formats: a zarch_float builtin rounds to the target and the trap ladder delivers; LOAD LENGTHENED is exact and IR alone (ruling R52, PoO 20-24 to 20-32, 20-45, 20-46)."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.conditional import pick
from interpreter.hlasm.data_movement import Source, from_gr32, from_gr64, sign_extended
from interpreter.hlasm.dfp_fields import INFINITY, SIGNALING_NAN
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, SHORT_DFP, DfpLayout
from interpreter.hlasm.dfp_operation import DfpOperation, dfp_builtin_name
from interpreter.hlasm.fp_slots import INVALID_BIT, QUANTUM_BIT
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.opcodes.dfp_ir import (
    EXPONENT,
    Fields,
    and_inexact_control,
    current_dfp_mode,
    decoded,
    dfp_modifier,
    encoded_at,
    fields_of,
    no_cc,
    quantum_control,
    quantum_yields,
    store_fields,
    stored,
)
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fp_forms import (
    GrStore,
    SuppressedBits,
    ieee_call,
    inexact_control,
    integer_stored,
    rounded_stored,
)
from interpreter.hlasm.opcodes.fp_ir import emit_ieee_ladder
from interpreter.hlasm.opcodes.fpr_images import (
    FIRST,
    FOURTH,
    SECOND,
    THIRD,
    compared,
    fpr,
)
from interpreter.hlasm.operands import optional_mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

INVALID_CONTROL = 0b1000

LAYOUTS: Mapping[str, DfpLayout] = {"D": LONG_DFP, "X": EXTENDED_DFP}


def _paired(
    layout: DfpLayout, operand: int, lowering: StatementLowering
) -> StatementLowering:
    if layout is EXTENDED_DFP:
        return pairs((operand,), lowering)
    return lowering


def _to_integer(
    operation: DfpOperation, store: GrStore, layout: DfpLayout
) -> StatementLowering:
    lowering = ieee_call(
        dfp_builtin_name(operation, layout),
        (dfp_modifier(SECOND), decoded(fpr(THIRD, layout), layout)),
        integer_stored(store),
        inexact_control,
    )
    return _paired(layout, THIRD, lowering)


_TO_INTEGERS: Mapping[str, tuple[DfpOperation, GrStore]] = {
    "CF": (DfpOperation.TO_FIXED_32, HlasmEmitter.store_gr32),
    "CG": (DfpOperation.TO_FIXED_64, HlasmEmitter.store_gr64),
    "CLF": (DfpOperation.TO_LOGICAL_32, HlasmEmitter.store_gr32),
    "CLG": (DfpOperation.TO_LOGICAL_64, HlasmEmitter.store_gr64),
}

TO_FIXED: Mapping[str, StatementLowering] = {
    f"{prefix}{letter}TR": _to_integer(operation, store, layout)
    for prefix, (operation, store) in _TO_INTEGERS.items()
    for letter, layout in LAYOUTS.items()
}


def _current(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return current_dfp_mode(emitter)


def _quantum_suppressed(statement: MachineStatement) -> int:
    return QUANTUM_BIT


def _from_integer(
    layout: DfpLayout,
    operands: tuple[Source, Source],
    suppressed: SuppressedBits,
) -> StatementLowering:
    mode, integer = operands
    lowering = ieee_call(
        dfp_builtin_name(DfpOperation.FROM_FIXED, layout),
        (mode, integer),
        stored(FIRST, layout, no_cc),
        suppressed,
        quantum_yields,
    )
    return _paired(layout, FIRST, lowering)


def _modified(layout: DfpLayout, integer: Source) -> StatementLowering:
    return _from_integer(
        layout,
        (dfp_modifier(SECOND), integer),
        and_inexact_control(quantum_control(SECOND), inexact_control),
    )


_SIGNED_64 = sign_extended(from_gr64(THIRD), 64)
_MODIFIED_SOURCES: Mapping[str, Source] = {
    "FTR": sign_extended(from_gr32(THIRD), 32),
    "GTRA": _SIGNED_64,
    "LFTR": from_gr32(THIRD),
    "LGTR": from_gr64(THIRD),
}

FROM_FIXED: Mapping[str, StatementLowering] = {
    **{
        f"C{letter}{kind}": _modified(layout, source)
        for kind, source in _MODIFIED_SOURCES.items()
        for letter, layout in LAYOUTS.items()
    },
    **{
        f"C{letter}GTR": _from_integer(
            layout,
            (_current, sign_extended(from_gr64(SECOND), 64)),
            _quantum_suppressed,
        )
        for letter, layout in LAYOUTS.items()
    },
}


def _keeps_specials(index: int) -> Callable[[MachineStatement], bool]:
    return lambda statement: bool(
        optional_mask_operand(statement, index, 0) & INVALID_CONTROL
    )


def _widened(emitter: HlasmEmitter, fields: Fields, delta: int, keeps: bool) -> Fields:
    sign, exponent, significand = fields
    finite = compared(emitter, BinopKind.GE, exponent, 0)
    moved = emitter.binop(BinopKind.ADD, exponent, emitter.int_(delta))
    if keeps:
        return sign, pick(emitter, finite, moved, exponent), significand
    signaling = compared(emitter, BinopKind.EQ, exponent, SIGNALING_NAN)
    quieted = emitter.binop(BinopKind.ADD, exponent, signaling)
    finite_or_nan = compared(emitter, BinopKind.NE, exponent, INFINITY)
    digits = emitter.binop(BinopKind.MUL, significand, finite_or_nan)
    return sign, pick(emitter, finite, moved, quieted), digits


def _lengthen(source: DfpLayout, target: DfpLayout) -> StatementLowering:
    delta = target.bias - source.bias

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        keeps = _keeps_specials(THIRD)(statement)
        fields = fields_of(
            emitter, decoded(fpr(SECOND, source), source)(emitter, statement)
        )
        result = _widened(emitter, fields, delta, keeps)
        signaling = compared(emitter, BinopKind.EQ, fields[EXPONENT], SIGNALING_NAN)
        invalid = emitter.binop(
            BinopKind.MUL, signaling, emitter.int_(INVALID_BIT * (not keeps))
        )
        none = emitter.int_(0)
        emit_ieee_ladder(
            emitter,
            IeeeOutcome(invalid, invalid, none, none),
            lambda slot: store_fields(
                emitter, reg_operand(statement, FIRST), target, result
            ),
        )

    return lower


def _round(source: DfpLayout, target: DfpLayout) -> StatementLowering:
    keeps = _keeps_specials(FOURTH)
    return ieee_call(
        dfp_builtin_name(DfpOperation.LOAD_ROUNDED, source),
        (
            dfp_modifier(SECOND),
            decoded(fpr(THIRD, source), source),
            lambda emitter, statement: emitter.int_(int(keeps(statement))),
        ),
        rounded_stored(source, target, encoded_at),
        and_inexact_control(quantum_control(SECOND), inexact_control),
        quantum_yields,
    )


LENGTHEN_ROUND: Mapping[str, StatementLowering] = {
    "LDETR": _lengthen(SHORT_DFP, LONG_DFP),
    "LXDTR": pairs((FIRST,), _lengthen(LONG_DFP, EXTENDED_DFP)),
    "LEDTR": _round(LONG_DFP, SHORT_DFP),
    "LDXTR": pairs((FIRST, THIRD), _round(EXTENDED_DFP, LONG_DFP)),
}


DFP_CONVERSION_LOWERINGS: Mapping[str, StatementLowering] = {
    **TO_FIXED,
    **{f"CG{letter}TRA": TO_FIXED[f"CG{letter}TR"] for letter in LAYOUTS},
    **FROM_FIXED,
    **LENGTHEN_ROUND,
}
