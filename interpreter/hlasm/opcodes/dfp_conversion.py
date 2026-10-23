# pyright: standard
"""DFP conversions to and from fixed point: IR decodes or reads the operand, a zarch_float builtin rounds to the target and the trap ladder delivers (ruling R52, PoO 20-24 to 20-32)."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_slots import QUANTUM_BIT
from interpreter.hlasm.data_movement import Source, from_gr32, from_gr64, sign_extended
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.dfp_operation import DfpOperation, dfp_builtin_name
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_conversion import GrStore, integer_stored
from interpreter.hlasm.opcodes.bfp_forms import (
    SuppressedBits,
    ieee_call,
    inexact_control,
)
from interpreter.hlasm.opcodes.dfp_ir import (
    and_inexact_control,
    current_dfp_mode,
    decoded,
    dfp_modifier,
    no_cc,
    quantum_control,
    quantum_yields,
    stored,
)
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import FIRST, SECOND, THIRD, fpr
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.register import Register

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

DFP_CONVERSION_LOWERINGS: Mapping[str, StatementLowering] = {
    **TO_FIXED,
    **{f"CG{letter}TRA": TO_FIXED[f"CG{letter}TR"] for letter in LAYOUTS},
    **FROM_FIXED,
}
