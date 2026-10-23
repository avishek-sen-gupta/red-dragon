# pyright: standard
"""PERFORM FLOATING-POINT OPERATION (ruling R52d, PoO 9-35 to 9-46): GR0's function word is decoded and checked in IR; the source in FPR 4 (6) is decoded by its family's IR, one builtin converts the radix, and the delivered value is encoded into FPR 0 (2) with the return code in GR1, alternate exception action included."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.bfp_layout import BfpLayout
from interpreter.hlasm.bfp_slots import (
    SCALED_SLOT,
    SCALING_BITS,
    SUPPRESSING_BITS,
)
from interpreter.hlasm.conditional import emit_either, emit_when
from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.dfp_layout import DfpLayout
from interpreter.hlasm.hfp_layout import HfpLayout
from interpreter.hlasm.hlasm_constants import (
    BYTE_MASK,
    FPC_VAR,
    LOW_WORD_MASK,
    PFPO_SOURCE_VAR,
    SPECIFICATION_EXCEPTION_ABEND,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.opcodes import hfp_ir
from interpreter.hlasm.opcodes.bfp_ir import (
    current_mode,
    enabled_traps,
    field_at,
    fields_list,
    image_at,
    outcome_of,
)
from interpreter.hlasm.opcodes.dfp_codec import DECODERS, ENCODERS
from interpreter.hlasm.opcodes.dfp_ir import (
    EXPONENT,
    SIGN,
    SIGNIFICAND,
    current_dfp_mode,
    quantum_yields,
)
from interpreter.hlasm.opcodes.floating_point_support import (
    DXC_FIELD,
    DXC_SHIFT,
    FLAG_SHIFT,
    emit_data_exception,
)
from interpreter.hlasm.opcodes.fpr_images import (
    compared,
    list_item,
    load_image,
    pick,
    store_image,
)
from interpreter.hlasm.packed_decimal import table_bit
from interpreter.hlasm.pfpo_formats import LAYOUTS, PFPO_BUILTIN, PfpoLayout
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.value_tree import emit_value_switch
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FUNCTION_REGISTER = 0
RETURN_REGISTER = 1
TARGET_FPR = 0
SOURCE_FPR = 4
TEST_SHIFT = 31
OPERATION_SHIFT = 24
OPERATION_MASK = 0x7F
CONVERT_RADIX = 0x01
TARGET_SHIFT = 16
SOURCE_SHIFT = 8
CONTROLS_SHIFT = 4
CONTROLS_MASK = 0b11
ALTERNATE_BIT = 0x40
METHOD_MASK = 0xF
DFP_METHOD = 0
BFP_METHOD = 1
BFP_RADIX = 1
VALID_FORMATS = sum(1 << code for code in LAYOUTS)
VALID_METHODS = 0b11111111_00000011
FIRST_BFP_CODE = 5
FIRST_DFP_CODE = 8
INVALID_FUNCTION_CC = 3
NONTRAP_CC = 1
ALTERNATE_CC = 2
SCALING_SLOT = 10
FORMAT_CODES = tuple(sorted(LAYOUTS))


def _field(emitter: HlasmEmitter, word: Register, shift: int, mask: int) -> Register:
    moved = emitter.binop(BinopKind.RSHIFT, word, emitter.int_(shift))
    return keep(mask)(emitter, moved)


def _radix(emitter: HlasmEmitter, code: Register) -> Register:
    return emitter.binop(
        BinopKind.ADD,
        compared(emitter, BinopKind.GE, code, FIRST_BFP_CODE),
        compared(emitter, BinopKind.GE, code, FIRST_DFP_CODE),
    )


def _all(emitter: HlasmEmitter, *bits: Register) -> Register:
    first, *rest = bits
    return (
        emitter.binop(BinopKind.BIT_AND, first, _all(emitter, *rest)) if rest else first
    )


def _valid(emitter: HlasmEmitter, word: Register) -> Register:
    target = _field(emitter, word, TARGET_SHIFT, BYTE_MASK)
    source = _field(emitter, word, SOURCE_SHIFT, BYTE_MASK)
    operation = _field(emitter, word, OPERATION_SHIFT, OPERATION_MASK)
    controls = _field(emitter, word, CONTROLS_SHIFT, CONTROLS_MASK)
    target_radix = _radix(emitter, target)
    bfp_target = compared(emitter, BinopKind.EQ, target_radix, BFP_RADIX)
    formats = emitter.int_(VALID_FORMATS)
    return _all(
        emitter,
        compared(emitter, BinopKind.EQ, operation, CONVERT_RADIX),
        table_bit(emitter, formats, target),
        table_bit(emitter, formats, source),
        emitter.binop(BinopKind.NE, target_radix, _radix(emitter, source)),
        table_bit(
            emitter, emitter.int_(VALID_METHODS), keep(METHOD_MASK)(emitter, word)
        ),
        emitter.binop(
            BinopKind.BIT_OR,
            emitter.binop(BinopKind.EQ, bfp_target, emitter.int_(0)),
            compared(emitter, BinopKind.EQ, controls, 0),
        ),
    )


def _set_return_code(emitter: HlasmEmitter, code: Register) -> None:
    emitter.store_gr32(RETURN_REGISTER, code)


def _tested(emitter: HlasmEmitter, valid: Register) -> None:
    invalid = emitter.binop(BinopKind.EQ, valid, emitter.int_(0))
    emitter.set_cc(
        emitter.binop(BinopKind.MUL, invalid, emitter.int_(INVALID_FUNCTION_CC))
    )
    _set_return_code(emitter, emitter.int_(0))


def _ieee_fields(
    emitter: HlasmEmitter, image: Register, layout: BfpLayout | DfpLayout
) -> Register:
    match layout:
        case BfpLayout():
            return fields_list(emitter, image, layout)
        case DfpLayout():
            return DECODERS[layout].call(emitter, (image,))


def _source_fields(emitter: HlasmEmitter, layout: PfpoLayout) -> Register:
    image = load_image(emitter, SOURCE_FPR, layout)
    if isinstance(layout, HfpLayout):
        return hfp_ir.fields_list(emitter, image, layout)
    return _ieee_fields(emitter, image, layout)


def _decoded_source(emitter: HlasmEmitter, word: Register) -> Register:
    code = _field(emitter, word, SOURCE_SHIFT, BYTE_MASK)

    def leaf(selected: int) -> None:
        fields = _source_fields(emitter, LAYOUTS[selected])
        emitter.emit_inst(StoreVar(name=PFPO_SOURCE_VAR, value_reg=fields))

    emit_value_switch(emitter, code, FORMAT_CODES, leaf)
    return emitter.load_var(PFPO_SOURCE_VAR)


def _method(emitter: HlasmEmitter, word: Register) -> Register:
    method = keep(METHOD_MASK)(emitter, word)
    return pick(
        emitter,
        compared(emitter, BinopKind.EQ, method, DFP_METHOD),
        current_dfp_mode(emitter),
        pick(
            emitter,
            compared(emitter, BinopKind.EQ, method, BFP_METHOD),
            current_mode(emitter),
            method,
        ),
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
            return ENCODERS[layout].call(emitter, _fields_at(emitter, result, slot))


def _target_image(
    emitter: HlasmEmitter, result: Register, slot: Register, layout: PfpoLayout
) -> Register:
    if isinstance(layout, HfpLayout):
        fields = _fields_at(emitter, result, slot)
        return hfp_ir.image_of(emitter, fields, layout, hfp_ir.true_zero_low)
    return _ieee_image(emitter, result, slot, layout)


def _fields_at(
    emitter: HlasmEmitter, result: Register, slot: Register
) -> tuple[Register, Register, Register]:
    first, second, third = (
        field_at(emitter, result, slot, at) for at in (SIGN, EXPONENT, SIGNIFICAND)
    )
    return first, second, third


def _deliver(
    emitter: HlasmEmitter, word: Register, result: Register, slot: Register
) -> None:
    code = _field(emitter, word, TARGET_SHIFT, BYTE_MASK)

    def leaf(selected: int) -> None:
        layout = LAYOUTS[selected]
        store_image(
            emitter, TARGET_FPR, layout, _target_image(emitter, result, slot, layout)
        )

    emit_value_switch(emitter, code, FORMAT_CODES, leaf)


def _alternate_or_trap(
    emitter: HlasmEmitter, word: Register, fpc: Register, dxc: Register
) -> None:
    alternate = emitter.binop(
        BinopKind.NE, keep(ALTERNATE_BIT)(emitter, word), emitter.int_(0)
    )

    def completed() -> None:
        shifted = emitter.binop(BinopKind.LSHIFT, dxc, emitter.int_(DXC_SHIFT))
        cleared = keep(LOW_WORD_MASK ^ DXC_FIELD)(emitter, fpc)
        emitter.emit_inst(
            StoreVar(
                name=FPC_VAR,
                value_reg=emitter.binop(BinopKind.BIT_OR, cleared, shifted),
            )
        )
        emitter.set_cc(emitter.int_(ALTERNATE_CC))

    emit_either(
        emitter, alternate, completed, lambda: emit_data_exception(emitter, fpc, dxc)
    )


def _flagged(
    emitter: HlasmEmitter, fpc: Register, outcome: IeeeOutcome, enabled: Register
) -> None:
    inverted = emitter.binop(BinopKind.BIT_XOR, enabled, emitter.int_(BYTE_MASK))
    raised = emitter.binop(BinopKind.BIT_AND, outcome.flags, inverted)
    moved = emitter.binop(BinopKind.LSHIFT, raised, emitter.int_(FLAG_SHIFT))
    flagged = emitter.binop(BinopKind.BIT_OR, fpc, moved)
    emitter.emit_inst(StoreVar(name=FPC_VAR, value_reg=flagged))
    trapped = emitter.binop(BinopKind.NE, enabled, emitter.int_(0))

    def nontrap() -> None:
        nonzero = emitter.binop(BinopKind.NE, raised, emitter.int_(0))
        emitter.set_cc(emitter.binop(BinopKind.MUL, nonzero, emitter.int_(NONTRAP_CC)))

    emit_either(
        emitter,
        trapped,
        lambda: emit_data_exception(emitter, flagged, outcome.inexact_dxc),
        nontrap,
    )


def _suppress_on(emitter: HlasmEmitter, fpc: Register, enabled: Register) -> None:
    suppressing = keep(SUPPRESSING_BITS)(emitter, enabled)
    emit_when(
        emitter,
        emitter.binop(BinopKind.NE, suppressing, emitter.int_(0)),
        lambda: emit_data_exception(emitter, fpc, suppressing),
    )


def _delivered(
    emitter: HlasmEmitter, word: Register, result: Register, enabled: Register
) -> Register:
    scaling = keep(SCALING_BITS)(emitter, enabled)
    scaled = emitter.binop(BinopKind.NE, scaling, emitter.int_(0))
    slot = emitter.binop(BinopKind.MUL, scaled, emitter.int_(SCALED_SLOT))
    _deliver(emitter, word, result, slot)
    exponent = list_item(emitter, result, SCALING_SLOT)
    _set_return_code(emitter, emitter.binop(BinopKind.MUL, scaled, exponent))
    return scaled


def _converted(emitter: HlasmEmitter, word: Register) -> None:
    fields = _decoded_source(emitter, word)
    result = emitter.call(PFPO_BUILTIN, (word, _method(emitter, word), fields))
    fpc = emitter.load_var(FPC_VAR)
    outcome = quantum_yields(emitter, fpc, outcome_of(emitter, result))
    enabled = enabled_traps(emitter, fpc, outcome.trap)
    _suppress_on(emitter, fpc, enabled)
    scaled = _delivered(emitter, word, result, enabled)
    emit_either(
        emitter,
        scaled,
        lambda: _alternate_or_trap(emitter, word, fpc, outcome.scaled_dxc),
        lambda: _flagged(emitter, fpc, outcome, enabled),
    )


def _lower_pfpo(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    word = emitter.load_gr32(FUNCTION_REGISTER)
    valid = _valid(emitter, word)
    testing = _field(emitter, word, TEST_SHIFT, 1)

    def performed() -> None:
        emit_when(
            emitter,
            emitter.binop(BinopKind.EQ, valid, emitter.int_(0)),
            lambda: emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND),
        )
        _converted(emitter, word)

    emit_either(emitter, testing, lambda: _tested(emitter, valid), performed)


PFPO_LOWERINGS: Mapping[str, StatementLowering] = {"PFPO": _lower_pfpo}
