# pyright: standard
"""DFP add, subtract, multiply and divide, with their A forms: IR decodes the operands, a zarch_float builtin rounds, the trap ladder delivers and IR encodes the result (ruling R49, PoO 20-19 to 20-21, 20-37, 20-47, 20-55)."""

from collections.abc import Mapping

from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.dfp_operation import DfpOperation, dfp_builtin_name
from interpreter.hlasm.opcodes.bfp_forms import ieee_call
from interpreter.hlasm.opcodes.dfp_ir import (
    AfterStore,
    decoded,
    dfp_modifier,
    no_cc,
    quantum_control,
    quantum_yields,
    set_fields_cc,
    stored,
)
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import FIRST, FOURTH, SECOND, THIRD, fpr
from interpreter.hlasm.statement_lowering import StatementLowering


def _arithmetic(
    operation: DfpOperation, layout: DfpLayout, after: AfterStore
) -> StatementLowering:
    return ieee_call(
        dfp_builtin_name(operation, layout),
        (
            dfp_modifier(FOURTH),
            decoded(fpr(SECOND, layout), layout),
            decoded(fpr(THIRD, layout), layout),
        ),
        stored(FIRST, layout, after),
        quantum_control(FOURTH),
        quantum_yields,
    )


def _forms(
    operation: DfpOperation, names: tuple[str, str, str, str], after: AfterStore
) -> Mapping[str, StatementLowering]:
    long, long_a, extended, extended_a = names
    long_form = _arithmetic(operation, LONG_DFP, after)
    extended_form = pairs(
        (FIRST, SECOND, THIRD), _arithmetic(operation, EXTENDED_DFP, after)
    )
    return {
        long: long_form,
        long_a: long_form,
        extended: extended_form,
        extended_a: extended_form,
    }


DFP_ARITHMETIC_LOWERINGS: Mapping[str, StatementLowering] = {
    **_forms(DfpOperation.ADD, ("ADTR", "ADTRA", "AXTR", "AXTRA"), set_fields_cc),
    **_forms(DfpOperation.SUBTRACT, ("SDTR", "SDTRA", "SXTR", "SXTRA"), set_fields_cc),
    **_forms(DfpOperation.MULTIPLY, ("MDTR", "MDTRA", "MXTR", "MXTRA"), no_cc),
    **_forms(DfpOperation.DIVIDE, ("DDTR", "DDTRA", "DXTR", "DXTRA"), no_cc),
}
