# pyright: standard
"""The Unicode conversions: R2's characters convert into R1 one at a time in one execution, ending with CC 0 when the second operand is exhausted, 1 when the first cannot hold the next result and 2 at an invalid character; both pairs then advance and count down by the bytes processed."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.compare_cc import emit_cc_constant
from interpreter.hlasm.conversion_cursor import ConversionCursor
from interpreter.hlasm.conversion_labels import ConversionLabels
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import register_address
from interpreter.hlasm.hlasm_constants import (
    CONVERT_SOURCE_AT_VAR,
    CONVERT_TARGET_AT_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import operand_pairs, store_progress
from interpreter.hlasm.opcodes.even_odd import even_odd_pairs
from interpreter.hlasm.operands import optional_mask_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.unicode_decoders import (
    UTF8_DECODERS,
    UTF16_DECODERS,
    UTF32_DECODERS,
    Decoder,
)
from interpreter.hlasm.unicode_encoders import (
    UTF8_ENCODER,
    UTF16_ENCODER,
    UTF32_ENCODER,
    Encoder,
)
from interpreter.instructions import Label_, StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Operand = tuple[Register, Register]

CONTROL_OPERAND = 2
NO_CONTROLS = 0
WELL_FORMEDNESS_CONTROL = 0b0001
EXHAUSTED_CC = 0
FULL_CC = 1
INVALID_CC = 2


def _labels(emitter: HlasmEmitter) -> ConversionLabels:
    return ConversionLabels(
        *(
            emitter.fresh_label(f"hl_cu_{name}")
            for name in ("loop", "exhausted", "invalid", "full", "basic", "supp")
        )
    )


def _start(emitter: HlasmEmitter) -> ConversionLabels:
    zero = emitter.int_(0)
    emitter.emit_inst(StoreVar(name=CONVERT_SOURCE_AT_VAR, value_reg=zero))
    emitter.emit_inst(StoreVar(name=CONVERT_TARGET_AT_VAR, value_reg=zero))
    labels = _labels(emitter)
    emitter.emit_inst(Label_(label=labels.loop))
    return labels


def _cursor(
    emitter: HlasmEmitter, operands: tuple[Operand, Operand]
) -> ConversionCursor:
    (target, target_length), (source, source_length) = operands
    source_at = emitter.load_var(CONVERT_SOURCE_AT_VAR)
    target_at = emitter.load_var(CONVERT_TARGET_AT_VAR)
    return ConversionCursor(
        source,
        source_at,
        emitter.binop(BinopKind.SUB, source_length, source_at),
        target,
        target_at,
        emitter.binop(BinopKind.SUB, target_length, target_at),
    )


def _operand(emitter: HlasmEmitter, r: int) -> Operand:
    return register_address(emitter, r), emitter.load_gr32(r + 1)


def _ends(emitter: HlasmEmitter, labels: ConversionLabels) -> None:
    done = emitter.fresh_label("hl_cu_done")
    emit_cc_constant(emitter, EXHAUSTED_CC, labels.exhausted, done)
    emit_cc_constant(emitter, FULL_CC, labels.full, done)
    emit_cc_constant(emitter, INVALID_CC, labels.invalid, done)
    emitter.emit_inst(Label_(label=done))


def _complete(
    emitter: HlasmEmitter,
    pairs: tuple[int, int],
    operands: tuple[Operand, Operand],
) -> None:
    offsets = (CONVERT_TARGET_AT_VAR, CONVERT_SOURCE_AT_VAR)
    _ = [
        _advance(emitter, r, operand, emitter.load_var(offset))
        for r, operand, offset in zip(pairs, operands, offsets, strict=True)
    ]


def _advance(emitter: HlasmEmitter, r: int, operand: Operand, at: Register) -> None:
    address, length = operand
    store_progress(
        emitter,
        r,
        emitter.binop(BinopKind.ADD, address, at),
        emitter.binop(BinopKind.SUB, length, at),
    )


def _step(
    emitter: HlasmEmitter,
    cursor: ConversionCursor,
    labels: ConversionLabels,
    coders: tuple[Decoder, Encoder],
) -> None:
    decoder, encoder = coders
    decoder(emitter, cursor, labels)
    encoder(emitter, cursor, labels)


def _convert(decoders: tuple[Decoder, Decoder], encoder: Encoder) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        controls = optional_mask_operand(statement, CONTROL_OPERAND, NO_CONTROLS)
        decoder = decoders[controls & WELL_FORMEDNESS_CONTROL]
        pairs = operand_pairs(statement)
        operands = (_operand(emitter, pairs[0]), _operand(emitter, pairs[1]))
        labels = _start(emitter)
        _step(emitter, _cursor(emitter, operands), labels, (decoder, encoder))
        _ends(emitter, labels)
        _complete(emitter, pairs, operands)

    return even_odd_pairs((FIRST_OPERAND, SECOND_OPERAND), lower)


CONVERT_UTF8_TO_UTF16 = _convert(UTF8_DECODERS, UTF16_ENCODER)
CONVERT_UTF8_TO_UTF32 = _convert(UTF8_DECODERS, UTF32_ENCODER)
CONVERT_UTF16_TO_UTF8 = _convert(UTF16_DECODERS, UTF8_ENCODER)
CONVERT_UTF16_TO_UTF32 = _convert(UTF16_DECODERS, UTF32_ENCODER)
CONVERT_UTF32_TO_UTF8 = _convert(UTF32_DECODERS, UTF8_ENCODER)
CONVERT_UTF32_TO_UTF16 = _convert(UTF32_DECODERS, UTF16_ENCODER)
