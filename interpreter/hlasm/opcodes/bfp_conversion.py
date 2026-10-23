# pyright: standard
"""BFP conversions: to and from fixed point and between BFP formats; rounding forms call a zarch_float builtin through the trap ladder, exact forms are IR (rulings R43-R45)."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_layout import (
    EXTENDED_LAYOUT,
    LONG_LAYOUT,
    SHORT_LAYOUT,
    BfpLayout,
)
from interpreter.hlasm.bfp_operation import BfpOperation
from interpreter.hlasm.bfp_slots import CC_SLOT
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_forms import (
    FIRST,
    SECOND,
    THIRD,
    Deliver,
    SuppressedBits,
    checked,
    fields,
    fpr,
    ieee,
    inexact_control,
    invalid_modifier,
    modifier,
    signals_all,
)
from interpreter.hlasm.opcodes.bfp_ir import list_item
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.register import Register

type GrStore = Callable[[HlasmEmitter, int, Register], None]

LAYOUTS: Mapping[str, BfpLayout] = {
    "E": SHORT_LAYOUT,
    "D": LONG_LAYOUT,
    "X": EXTENDED_LAYOUT,
}


def _store_gr32(emitter: HlasmEmitter, r: int, value: Register) -> None:
    emitter.store_gr32(r, value)


def _store_gr64(emitter: HlasmEmitter, r: int, value: Register) -> None:
    emitter.store_gr64(r, value)


def _integer_stored(store: GrStore) -> Deliver:
    def deliver(
        emitter: HlasmEmitter,
        statement: MachineStatement,
        result: Register,
        slot: Register,
    ) -> None:
        store(emitter, reg_operand(statement, FIRST), list_item(emitter, result, 0))
        emitter.set_cc(list_item(emitter, result, CC_SLOT))

    return deliver


def _with_pair(
    layout: BfpLayout, operands: tuple[int, ...], lowering: StatementLowering
) -> StatementLowering:
    if layout is EXTENDED_LAYOUT:
        return pairs(operands, lowering)
    return lowering


def _to_integer(
    operation: BfpOperation,
    store: GrStore,
    layout: BfpLayout,
    suppressed: SuppressedBits,
) -> StatementLowering:
    lowering = ieee(
        (operation, layout),
        (modifier(SECOND), fields(fpr(THIRD, layout), layout)),
        _integer_stored(store),
        suppressed,
    )
    return checked(invalid_modifier(SECOND), _with_pair(layout, (THIRD,), lowering))


_SIGNED_FORMS: Mapping[str, SuppressedBits] = {
    "BR": signals_all,
    "BRA": inexact_control,
}
_LOGICAL_FORMS: Mapping[str, SuppressedBits] = {"BR": inexact_control}
_INTEGERS: Mapping[str, tuple[BfpOperation, GrStore, Mapping[str, SuppressedBits]]] = {
    "CF": (BfpOperation.TO_FIXED_32, _store_gr32, _SIGNED_FORMS),
    "CG": (BfpOperation.TO_FIXED_64, _store_gr64, _SIGNED_FORMS),
    "CLF": (BfpOperation.TO_LOGICAL_32, _store_gr32, _LOGICAL_FORMS),
    "CLG": (BfpOperation.TO_LOGICAL_64, _store_gr64, _LOGICAL_FORMS),
}

TO_FIXED: Mapping[str, StatementLowering] = {
    f"{prefix}{letter}{suffix}": _to_integer(operation, store, layout, suppressed)
    for prefix, (operation, store, forms) in _INTEGERS.items()
    for letter, layout in LAYOUTS.items()
    for suffix, suppressed in forms.items()
}

BFP_CONVERSION_LOWERINGS: Mapping[str, StatementLowering] = {
    **TO_FIXED,
}
