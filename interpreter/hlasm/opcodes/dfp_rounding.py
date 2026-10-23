# pyright: standard
"""DFP LOAD FP INTEGER, QUANTIZE and REROUND: IR decodes the operands, a zarch_float builtin rounds by the M field, and the trap ladder delivers the encoded result (PoO 20-42 to 20-44, 20-49 to 20-53)."""

from collections.abc import Mapping

from interpreter.hlasm.data_movement import from_gr64, keep
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.dfp_operation import DfpOperation, dfp_builtin_name
from interpreter.hlasm.opcodes.bfp_forms import ieee_call, inexact_control
from interpreter.hlasm.opcodes.dfp_ir import (
    and_inexact_control,
    decoded,
    dfp_modifier,
    no_cc,
    quantum_control,
    stored,
)
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import FIRST, FOURTH, SECOND, THIRD, fpr
from interpreter.hlasm.statement_lowering import StatementLowering

SIGNIFICANCE_BITS = 0b111111


def _integral(layout: DfpLayout) -> StatementLowering:
    return ieee_call(
        dfp_builtin_name(DfpOperation.ROUND_TO_INTEGRAL, layout),
        (dfp_modifier(SECOND), decoded(fpr(THIRD, layout), layout)),
        stored(FIRST, layout, no_cc),
        and_inexact_control(quantum_control(SECOND), inexact_control),
    )


def _quantize(layout: DfpLayout) -> StatementLowering:
    return ieee_call(
        dfp_builtin_name(DfpOperation.QUANTIZE, layout),
        (
            dfp_modifier(FOURTH),
            decoded(fpr(SECOND, layout), layout),
            decoded(fpr(THIRD, layout), layout),
        ),
        stored(FIRST, layout, no_cc),
        quantum_control(FOURTH),
    )


def _reround(layout: DfpLayout) -> StatementLowering:
    return ieee_call(
        dfp_builtin_name(DfpOperation.REROUND, layout),
        (
            dfp_modifier(FOURTH),
            decoded(fpr(SECOND, layout), layout),
            lambda emitter, statement: keep(SIGNIFICANCE_BITS)(
                emitter, from_gr64(THIRD)(emitter, statement)
            ),
        ),
        stored(FIRST, layout, no_cc),
        quantum_control(FOURTH),
    )


DFP_ROUNDING_LOWERINGS: Mapping[str, StatementLowering] = {
    "FIDTR": _integral(LONG_DFP),
    "FIXTR": pairs((FIRST, THIRD), _integral(EXTENDED_DFP)),
    "QADTR": _quantize(LONG_DFP),
    "QAXTR": pairs((FIRST, SECOND, THIRD), _quantize(EXTENDED_DFP)),
    "RRDTR": _reround(LONG_DFP),
    "RRXTR": pairs((FIRST, SECOND), _reround(EXTENDED_DFP)),
}
