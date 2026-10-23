# pyright: standard
"""HFP conversions: rounding to fixed point and to BFP through a zarch_float builtin; the exact and truncating forms in IR (ruling R47)."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_layout import LONG_LAYOUT as LONG_BFP
from interpreter.hlasm.bfp_layout import SHORT_LAYOUT as SHORT_BFP
from interpreter.hlasm.bfp_layout import BfpLayout
from interpreter.hlasm.hfp_layout import EXTENDED_HFP, LONG_HFP, SHORT_HFP, HfpLayout
from interpreter.hlasm.hfp_operation import HfpOperation
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_forms import checked
from interpreter.hlasm.opcodes.bfp_ir import image_at
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import (
    FIRST,
    SECOND,
    THIRD,
    fpr,
    list_item,
    store_image,
)
from interpreter.hlasm.opcodes.hfp_arithmetic import Deliver, field_sources, hfp_call
from interpreter.hlasm.operands import mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.register import Register
from zarch_float.rounding_mode import (
    HFP_MODIFIER_MODES,
    HFP_TO_BFP_MODIFIER_MODES,
    RoundingMode,
)

type GrDeliver = Callable[[HlasmEmitter, int, Register], None]

INTEGER_SLOT = 0
INTEGER_CC_SLOT = 1
BFP_CC_SLOT = 3
LAYOUTS: Mapping[str, HfpLayout] = {"E": SHORT_HFP, "D": LONG_HFP, "X": EXTENDED_HFP}


def _m3(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return emitter.int_(mask_operand(statement, SECOND))


def _invalid(modes: Mapping[int, RoundingMode]) -> Callable[[MachineStatement], bool]:
    return lambda statement: mask_operand(statement, SECOND) not in modes


def _rounded(
    builtin: tuple[HfpOperation, HfpLayout], store: Deliver
) -> StatementLowering:
    layout = builtin[1]
    arguments = (_m3, *field_sources(layout, (fpr(THIRD, layout),)))
    return hfp_call(builtin, arguments, store)


def _integer_into(gr_store: GrDeliver) -> Deliver:
    def store(
        emitter: HlasmEmitter,
        statement: MachineStatement,
        result: Register,
        zeroed: Register,
    ) -> None:
        value = list_item(emitter, result, INTEGER_SLOT)
        gr_store(emitter, reg_operand(statement, FIRST), value)
        emitter.set_cc(list_item(emitter, result, INTEGER_CC_SLOT))

    return store


def _bfp_into(target: BfpLayout) -> Deliver:
    def store(
        emitter: HlasmEmitter,
        statement: MachineStatement,
        result: Register,
        zeroed: Register,
    ) -> None:
        image = image_at(emitter, result, emitter.int_(0), target)
        store_image(emitter, reg_operand(statement, FIRST), target, image)
        emitter.set_cc(list_item(emitter, result, BFP_CC_SLOT))

    return store


def _store_gr32(emitter: HlasmEmitter, r: int, value: Register) -> None:
    emitter.store_gr32(r, value)


def _store_gr64(emitter: HlasmEmitter, r: int, value: Register) -> None:
    emitter.store_gr64(r, value)


def _to_fixed(
    operation: HfpOperation, gr_store: GrDeliver, layout: HfpLayout
) -> StatementLowering:
    lowering = _rounded((operation, layout), _integer_into(gr_store))
    paired = pairs((THIRD,), lowering) if layout is EXTENDED_HFP else lowering
    return checked(_invalid(HFP_MODIFIER_MODES), paired)


_FIXED: Mapping[str, tuple[HfpOperation, GrDeliver]] = {
    "CF": (HfpOperation.TO_FIXED_32, _store_gr32),
    "CG": (HfpOperation.TO_FIXED_64, _store_gr64),
}

TO_FIXED: Mapping[str, StatementLowering] = {
    f"{prefix}{letter}R": _to_fixed(operation, gr_store, layout)
    for prefix, (operation, gr_store) in _FIXED.items()
    for letter, layout in LAYOUTS.items()
}

TO_BFP: Mapping[str, StatementLowering] = {
    name: checked(
        _invalid(HFP_TO_BFP_MODIFIER_MODES),
        _rounded((operation, LONG_HFP), _bfp_into(target)),
    )
    for name, operation, target in (
        ("TBEDR", HfpOperation.TO_BFP_SHORT, SHORT_BFP),
        ("TBDR", HfpOperation.TO_BFP_LONG, LONG_BFP),
    )
}

HFP_CONVERSION_LOWERINGS: Mapping[str, StatementLowering] = {**TO_FIXED, **TO_BFP}
