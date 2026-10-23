# pyright: standard
"""PERFORM FLOATING-POINT OPERATION (ruling R52d, PoO 9-35 to 9-46): GR0's function word is decoded and checked in IR; the source in FPR 4 (6) is decoded by its family's IR, one builtin converts the radix, and the delivered value is encoded into FPR 0 (2) with the return code in GR1, alternate exception action included."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.conditional import emit_either, emit_when, pick
from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.hlasm_constants import (
    FPC_VAR,
    SPECIFICATION_EXCEPTION_ABEND,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import IrFunction
from interpreter.hlasm.ladder_end import LadderEnd, ScaledTrap
from interpreter.hlasm.opcodes.bfp_ir import bfp_mode_of
from interpreter.hlasm.opcodes.dfp_ir import (
    DFP_FPC_TO_MODIFIER,
    quantum_yields,
)
from interpreter.hlasm.opcodes.floating_point_support import (
    DFP_MODE_SHIFT,
    emit_data_exception,
    store_dxc,
)
from interpreter.hlasm.opcodes.fp_ir import emit_ieee_ladder, mode_code_of, outcome_of
from interpreter.hlasm.opcodes.fpr_images import (
    compared,
    list_item,
    load_image,
    store_image,
)
from interpreter.hlasm.opcodes.pfpo_codec import (
    FPR_PAIR,
    PFPO_DECODE,
    PFPO_ENCODE,
    SOURCE_SHIFT,
    TARGET_SHIFT,
    format_code,
    word_field,
)
from interpreter.hlasm.packed_decimal import table_bit
from interpreter.hlasm.pfpo_formats import LAYOUTS, PFPO_BUILTIN
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import Branch, Label_
from interpreter.ir import CodeLabel
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


def _valid(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
    (word,) = parameters
    target = format_code(emitter, word, TARGET_SHIFT)
    source = format_code(emitter, word, SOURCE_SHIFT)
    operation = word_field(emitter, word, OPERATION_SHIFT, OPERATION_MASK)
    controls = word_field(emitter, word, CONTROLS_SHIFT, CONTROLS_MASK)
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


def _method(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
    word, fpc = parameters
    method = keep(METHOD_MASK)(emitter, word)
    dfp_mode = mode_code_of(emitter, fpc, DFP_MODE_SHIFT, DFP_FPC_TO_MODIFIER)
    return pick(
        emitter,
        compared(emitter, BinopKind.EQ, method, DFP_METHOD),
        dfp_mode,
        pick(
            emitter,
            compared(emitter, BinopKind.EQ, method, BFP_METHOD),
            bfp_mode_of(emitter, fpc),
            method,
        ),
    )


PFPO_VALID = IrFunction("__hlasm_pfpo_valid", 1, _valid)
PFPO_METHOD = IrFunction("__hlasm_pfpo_method", 2, _method)


def _alternate_or_trap(word: Register, done: CodeLabel) -> ScaledTrap:
    def trap(emitter: HlasmEmitter, fpc: Register, dxc: Register) -> None:
        alternate = emitter.binop(
            BinopKind.NE, keep(ALTERNATE_BIT)(emitter, word), emitter.int_(0)
        )

        def completed() -> None:
            store_dxc(emitter, fpc, dxc)
            emitter.set_cc(emitter.int_(ALTERNATE_CC))
            emitter.emit_inst(Branch(label=done))

        emit_when(emitter, alternate, completed)
        emit_data_exception(emitter, fpc, dxc)

    return trap


def _nontrap_cc(emitter: HlasmEmitter, raised: Register) -> None:
    nonzero = emitter.binop(BinopKind.NE, raised, emitter.int_(0))
    emitter.set_cc(emitter.binop(BinopKind.MUL, nonzero, emitter.int_(NONTRAP_CC)))


def _delivered(
    emitter: HlasmEmitter, word: Register, result: Register
) -> Callable[[Register], None]:
    def deliver(slot: Register) -> None:
        old = load_image(emitter, TARGET_FPR, FPR_PAIR)
        image = PFPO_ENCODE.call(emitter, (word, result, slot, old))
        store_image(emitter, TARGET_FPR, FPR_PAIR, image)
        exponent = list_item(emitter, result, SCALING_SLOT)
        scaled = emitter.binop(BinopKind.NE, slot, emitter.int_(0))
        _set_return_code(emitter, emitter.binop(BinopKind.MUL, scaled, exponent))

    return deliver


def _converted(emitter: HlasmEmitter, word: Register) -> None:
    source = load_image(emitter, SOURCE_FPR, FPR_PAIR)
    fields = PFPO_DECODE.call(emitter, (word, source))
    method = PFPO_METHOD.call(emitter, (word, emitter.load_var(FPC_VAR)))
    result = emitter.call(PFPO_BUILTIN, (word, method, fields))
    done = emitter.fresh_label("hl_pfpo_done")
    emit_ieee_ladder(
        emitter,
        outcome_of(emitter, result),
        _delivered(emitter, word, result),
        quantum_yields,
        LadderEnd(_alternate_or_trap(word, done), _nontrap_cc),
    )
    emitter.emit_inst(Label_(label=done))


def _lower_pfpo(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    word = emitter.load_gr32(FUNCTION_REGISTER)
    valid = PFPO_VALID.call(emitter, (word,))
    testing = word_field(emitter, word, TEST_SHIFT, 1)

    def performed() -> None:
        emit_when(
            emitter,
            emitter.binop(BinopKind.EQ, valid, emitter.int_(0)),
            lambda: emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND),
        )
        _converted(emitter, word)

    emit_either(emitter, testing, lambda: _tested(emitter, valid), performed)


PFPO_LOWERINGS: Mapping[str, StatementLowering] = {"PFPO": _lower_pfpo}
