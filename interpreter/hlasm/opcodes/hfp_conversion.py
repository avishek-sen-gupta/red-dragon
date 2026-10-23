# pyright: standard
"""HFP conversions: rounding to fixed point and to BFP through a zarch_float builtin; the exact and truncating forms in IR (ruling R47)."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_layout import LONG_LAYOUT as LONG_BFP
from interpreter.hlasm.bfp_layout import SHORT_LAYOUT as SHORT_BFP
from interpreter.hlasm.bfp_layout import BfpLayout
from interpreter.hlasm.data_movement import (
    Source,
    from_gr32,
    from_gr64,
    keep,
    sign_extended,
)
from interpreter.hlasm.hfp_layout import EXTENDED_HFP, LONG_HFP, SHORT_HFP, HfpLayout
from interpreter.hlasm.hfp_operation import HfpOperation
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_forms import checked
from interpreter.hlasm.opcodes.bfp_ir import image_at, nan_of, significand_of
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.opcodes.fpr_images import (
    FIRST,
    SECOND,
    THIRD,
    fpr,
    list_item,
    pick,
    signed_magnitude,
    store_image,
)
from interpreter.hlasm.opcodes.hfp_arithmetic import Deliver, field_sources, hfp_call
from interpreter.hlasm.opcodes.hfp_ir import image_of, normalized_fields, true_zero_low
from interpreter.hlasm.operands import mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from zarch_float.rounding_mode import (
    HFP_MODIFIER_MODES,
    HFP_TO_BFP_MODIFIER_MODES,
    RoundingMode,
)

type GrStore = Callable[[HlasmEmitter, int, Register], None]

INTEGER_SLOT = 0
INTEGER_CC_SLOT = 1
BFP_CC_SLOT = 3
MAX_CHARACTERISTIC = 127
SPECIAL_CC = 3
POSITIVE_CC = 2
LARGEST_MAGNITUDE = (1 << LONG_HFP.sign_shift) - 1
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


def _integer_into(gr_store: GrStore) -> Deliver:
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
    operation: HfpOperation, gr_store: GrStore, layout: HfpLayout
) -> StatementLowering:
    lowering = _rounded((operation, layout), _integer_into(gr_store))
    paired = pairs((THIRD,), lowering) if layout is EXTENDED_HFP else lowering
    return checked(_invalid(HFP_MODIFIER_MODES), paired)


_FIXED: Mapping[str, tuple[HfpOperation, GrStore]] = {
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


def _from_integer(layout: HfpLayout, integer: Source) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        negative, magnitude = signed_magnitude(emitter, integer(emitter, statement))
        binary = (magnitude, emitter.int_(0))
        fields = normalized_fields(emitter, negative, binary, layout)
        image = image_of(emitter, fields, layout, true_zero_low)
        store_image(emitter, reg_operand(statement, FIRST), layout, image)

    return pairs((FIRST,), lower) if layout is EXTENDED_HFP else lower


_INTEGERS: Mapping[str, Source] = {
    "F": sign_extended(from_gr32(SECOND), 32),
    "G": sign_extended(from_gr64(SECOND), 64),
}

FROM_FIXED: Mapping[str, StatementLowering] = {
    f"C{letter}{kind}R": _from_integer(layout, integer)
    for kind, integer in _INTEGERS.items()
    for letter, layout in LAYOUTS.items()
}


def _either(emitter: HlasmEmitter, a: Register, b: Register) -> Register:
    return emitter.binop(BinopKind.BIT_OR, a, b)


def _overflow(
    emitter: HlasmEmitter, biased: Register, characteristic: Register, source: BfpLayout
) -> Register:
    special = emitter.binop(BinopKind.EQ, biased, emitter.int_(source.exponent_mask))
    too_large = emitter.binop(
        BinopKind.GT, characteristic, emitter.int_(MAX_CHARACTERISTIC)
    )
    return _either(emitter, special, too_large)


def _largest(
    emitter: HlasmEmitter, image: Register, signed_zero: Register, source: BfpLayout
) -> Register:
    numeric = emitter.binop(
        BinopKind.SUB, emitter.int_(1), nan_of(emitter, image, source)
    )
    signed = emitter.binop(BinopKind.MUL, numeric, signed_zero)
    return _either(emitter, signed, emitter.int_(LARGEST_MAGNITUDE))


def _signed_cc(emitter: HlasmEmitter, sign: Register, magnitude: Register) -> Register:
    nonzero = emitter.binop(BinopKind.NE, magnitude, emitter.int_(0))
    signed = emitter.binop(BinopKind.SUB, emitter.int_(POSITIVE_CC), sign)
    return emitter.binop(BinopKind.MUL, nonzero, signed)


def _finite(
    emitter: HlasmEmitter,
    fields: tuple[Register, Register, Register],
    signed_zero: Register,
) -> Register:
    underflow = emitter.binop(BinopKind.LT, fields[1], emitter.int_(0))
    exact = image_of(emitter, fields, LONG_HFP, true_zero_low)
    return pick(emitter, underflow, signed_zero, exact)


def _hfp_image(
    emitter: HlasmEmitter, image: Register, source: BfpLayout
) -> tuple[Register, Register]:
    sign = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(source.sign_shift))
    shifted = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(source.fraction_bits))
    biased = keep(source.exponent_mask)(emitter, shifted)
    binary = significand_of(emitter, image, biased, source)
    fields = normalized_fields(emitter, sign, binary, LONG_HFP)
    overflow = _overflow(emitter, biased, fields[1], source)
    signed_zero = emitter.binop(
        BinopKind.LSHIFT, sign, emitter.int_(LONG_HFP.sign_shift)
    )
    largest = _largest(emitter, image, signed_zero, source)
    return (
        pick(emitter, overflow, largest, _finite(emitter, fields, signed_zero)),
        pick(
            emitter,
            overflow,
            emitter.int_(SPECIAL_CC),
            _signed_cc(emitter, sign, binary[0]),
        ),
    )


def _from_bfp(source: BfpLayout) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        operand = fpr(SECOND, source)(emitter, statement)
        image, cc = _hfp_image(emitter, operand, source)
        store_image(emitter, reg_operand(statement, FIRST), LONG_HFP, image)
        emitter.set_cc(cc)

    return lower


FROM_BFP: Mapping[str, StatementLowering] = {
    "THDER": _from_bfp(SHORT_BFP),
    "THDR": _from_bfp(LONG_BFP),
}

HFP_CONVERSION_LOWERINGS: Mapping[str, StatementLowering] = {
    **TO_FIXED,
    **TO_BFP,
    **FROM_FIXED,
    **FROM_BFP,
}
