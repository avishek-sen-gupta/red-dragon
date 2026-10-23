# pyright: standard
"""PFPO's two format dispatches as IR functions defined once per program (ruling R51): the FPR 4 and 6 image to the builtin's field list by GR0's source format, and the delivered result merged into the FPR 0 and 2 image by GR0's target format, each through its family's IR."""

from collections.abc import Callable, Sequence

from interpreter.hlasm.bfp_layout import BfpLayout
from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, DfpLayout
from interpreter.hlasm.fpr_layout import FprLayout
from interpreter.hlasm.hfp_layout import HfpLayout
from interpreter.hlasm.hlasm_constants import BYTE_MASK, PFPO_FORMAT_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import IrFunction
from interpreter.hlasm.opcodes import hfp_ir
from interpreter.hlasm.opcodes.bfp_ir import fields_list, image_at
from interpreter.hlasm.opcodes.dfp_codec import DECODERS
from interpreter.hlasm.opcodes.dfp_ir import encoded_at, fields_at
from interpreter.hlasm.pfpo_formats import LAYOUTS, PfpoLayout
from interpreter.hlasm.value_tree import emit_value_switch
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FPR_PAIR: FprLayout = EXTENDED_DFP
TARGET_SHIFT = 16
SOURCE_SHIFT = 8
FORMAT_CODES = tuple(sorted(LAYOUTS))

type Leaf = Callable[[PfpoLayout], Register]


def format_code(emitter: HlasmEmitter, word: Register, shift: int) -> Register:
    moved = emitter.binop(BinopKind.RSHIFT, word, emitter.int_(shift))
    return keep(BYTE_MASK)(emitter, moved)


def _switched(emitter: HlasmEmitter, code: Register, leaf: Leaf) -> Register:
    def stored(selected: int) -> None:
        value = leaf(LAYOUTS[selected])
        emitter.emit_inst(StoreVar(name=PFPO_FORMAT_VAR, value_reg=value))

    emit_value_switch(emitter, code, FORMAT_CODES, stored)
    return emitter.load_var(PFPO_FORMAT_VAR)


def _unused_bits(layout: PfpoLayout) -> int:
    return FPR_PAIR.width - layout.width


def _ieee_fields(
    emitter: HlasmEmitter, image: Register, layout: BfpLayout | DfpLayout
) -> Register:
    match layout:
        case BfpLayout():
            return fields_list(emitter, image, layout)
        case DfpLayout():
            return DECODERS[layout].call(emitter, (image,))


def _source_fields(
    emitter: HlasmEmitter, pair: Register, layout: PfpoLayout
) -> Register:
    image = emitter.binop(BinopKind.RSHIFT, pair, emitter.int_(_unused_bits(layout)))
    if isinstance(layout, HfpLayout):
        return hfp_ir.fields_list(emitter, image, layout)
    return _ieee_fields(emitter, image, layout)


def _decode(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
    word, pair = parameters
    code = format_code(emitter, word, SOURCE_SHIFT)
    return _switched(
        emitter, code, lambda layout: _source_fields(emitter, pair, layout)
    )


def _ieee_image(
    emitter: HlasmEmitter,
    result: Register,
    slot: Register,
    layout: BfpLayout | DfpLayout,
) -> Register:
    match layout:
        case BfpLayout():
            return image_at(emitter, result, slot, layout)
        case DfpLayout():
            return encoded_at(emitter, result, slot, layout)


def _target_image(
    emitter: HlasmEmitter, result: Register, slot: Register, layout: PfpoLayout
) -> Register:
    if isinstance(layout, HfpLayout):
        fields = fields_at(emitter, result, slot)
        return hfp_ir.image_of(emitter, fields, layout, hfp_ir.true_zero_low)
    return _ieee_image(emitter, result, slot, layout)


def _merged(
    emitter: HlasmEmitter, image: Register, old: Register, layout: PfpoLayout
) -> Register:
    unused = _unused_bits(layout)
    placed = emitter.binop(BinopKind.LSHIFT, image, emitter.int_(unused))
    kept = keep((1 << unused) - 1)(emitter, old)
    return emitter.binop(BinopKind.BIT_OR, placed, kept)


def _encode(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
    word, result, slot, old = parameters
    code = format_code(emitter, word, TARGET_SHIFT)
    return _switched(
        emitter,
        code,
        lambda layout: _merged(
            emitter, _target_image(emitter, result, slot, layout), old, layout
        ),
    )


PFPO_DECODE = IrFunction("__hlasm_pfpo_decode", 2, _decode)
PFPO_ENCODE = IrFunction("__hlasm_pfpo_encode", 4, _encode)
