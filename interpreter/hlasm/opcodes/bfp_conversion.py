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
from interpreter.hlasm.data_movement import (
    Source,
    from_gr32,
    from_gr64,
    sign_extended,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_forms import (
    FIRST,
    SECOND,
    THIRD,
    Deliver,
    SuppressedBits,
    checked,
    current,
    fields,
    fpr,
    ieee,
    inexact_control,
    invalid_modifier,
    modifier,
    no_cc,
    signals_all,
    stored,
)
from interpreter.hlasm.opcodes.bfp_ir import exact_image, list_item, store_image
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type GrStore = Callable[[HlasmEmitter, int, Register], None]
type GrRead = Callable[[int], Source]

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


def _signed(read: GrRead, bits: int) -> GrRead:
    return lambda index: sign_extended(read(index), bits)


def _from_exact(layout: BfpLayout, integer: Source) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        value = integer(emitter, statement)
        negative = emitter.binop(BinopKind.LT, value, emitter.int_(0))
        doubled = emitter.binop(BinopKind.MUL, negative, emitter.int_(2))
        flipped = emitter.binop(BinopKind.MUL, doubled, value)
        magnitude = emitter.binop(BinopKind.SUB, value, flipped)
        image = exact_image(emitter, negative, magnitude, emitter.int_(0), layout)
        store_image(emitter, reg_operand(statement, FIRST), layout, image)

    return lower


def _from_integer(
    layout: BfpLayout,
    source: tuple[GrRead, int],
    operands: tuple[int, Source],
    suppressed: SuppressedBits,
) -> StatementLowering:
    read, bits = source
    r2, mode = operands
    lowering = (
        _from_exact(layout, read(r2))
        if bits <= layout.format.precision
        else ieee(
            (BfpOperation.FROM_FIXED, layout),
            (mode, read(r2)),
            stored(FIRST, layout, no_cc),
            suppressed,
        )
    )
    return _with_pair(layout, (FIRST,), lowering)


def _modified(layout: BfpLayout, source: tuple[GrRead, int]) -> StatementLowering:
    return checked(
        invalid_modifier(SECOND),
        _from_integer(layout, source, (THIRD, modifier(SECOND)), inexact_control),
    )


_SIGNED_SOURCES: Mapping[str, tuple[GrRead, int]] = {
    "F": (_signed(from_gr32, 32), 32),
    "G": (_signed(from_gr64, 64), 64),
}
_LOGICAL_SOURCES: Mapping[str, tuple[GrRead, int]] = {
    "LF": (from_gr32, 32),
    "LG": (from_gr64, 64),
}

FROM_FIXED: Mapping[str, StatementLowering] = {
    **{
        f"C{letter}{kind}BR": _from_integer(
            layout, source, (SECOND, current), signals_all
        )
        for kind, source in _SIGNED_SOURCES.items()
        for letter, layout in LAYOUTS.items()
    },
    **{
        f"C{letter}{kind}BRA": _modified(layout, source)
        for kind, source in _SIGNED_SOURCES.items()
        for letter, layout in LAYOUTS.items()
    },
    **{
        f"C{letter}{kind}BR": _modified(layout, source)
        for kind, source in _LOGICAL_SOURCES.items()
        for letter, layout in LAYOUTS.items()
    },
}

BFP_CONVERSION_LOWERINGS: Mapping[str, StatementLowering] = {
    **TO_FIXED,
    **FROM_FIXED,
}
