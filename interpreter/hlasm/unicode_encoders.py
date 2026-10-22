# pyright: standard
"""The Unicode conversions' target writers: each takes the decoded code point at its basic-plane or supplementary entry, stops when the first operand cannot hold the result, and otherwise stores the UTF-8, UTF-16 or UTF-32 character and moves both offsets on."""

from collections.abc import Callable, Mapping

from interpreter.hlasm.bit_fields import combined_bits, placed_bits
from interpreter.hlasm.conversion_cursor import ConversionCursor
from interpreter.hlasm.conversion_labels import ConversionLabels
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    BYTE_MASK,
    CODE_POINT_VAR,
    CONVERT_NEXT_SOURCE_VAR,
    CONVERT_SOURCE_AT_VAR,
    CONVERT_TARGET_AT_VAR,
    HALFWORD_BITS,
    HALFWORD_BYTES,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.range_dispatch import emit_range_dispatch
from interpreter.instructions import Branch, BranchIf, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Encoder = Callable[[HlasmEmitter, ConversionCursor, ConversionLabels], None]

CONTINUATION_TAG = 0x80
CONTINUATION_BITS = 0x3F
CONTINUATION_SHIFT = 6
UTF8_LEADS: Mapping[int, tuple[int, int]] = {
    1: (0x00, 0x7F),
    2: (0xC0, 0x1F),
    3: (0xE0, 0x0F),
    4: (0xF0, 0x07),
}
UTF8_ONE_BYTE_END = 0x80
UTF8_TWO_BYTE_END = 0x800
UTF8_SUPPLEMENTARY = 4
HIGH_SURROGATE = 0xD800
LOW_SURROGATE = 0xDC00
PLANE_BITS = 0xF
PLANE_SHIFT = 6
HIGH_PAYLOAD_BITS = 0x3F
HIGH_PAYLOAD_SHIFT = 10
LOW_PAYLOAD_BITS = 0x3FF


def _require_room(
    emitter: HlasmEmitter, cursor: ConversionCursor, width: int, full: CodeLabel
) -> None:
    room = emitter.fresh_label("hl_cu_room")
    short = emitter.binop(BinopKind.LT, cursor.target_left, emitter.int_(width))
    emitter.emit_inst(BranchIf(cond_reg=short, branch_targets=(full, room)))
    emitter.emit_inst(Label_(label=room))


def _store(
    emitter: HlasmEmitter,
    cursor: ConversionCursor,
    labels: ConversionLabels,
    character: tuple[Register, int],
) -> None:
    value, width = character
    _require_room(emitter, cursor, width, labels.full)
    emitter.write_bytes(
        cursor.target, cursor.target_at, width, emitter.image(value, width)
    )
    stored = emitter.binop(BinopKind.ADD, cursor.target_at, emitter.int_(width))
    emitter.emit_inst(StoreVar(name=CONVERT_TARGET_AT_VAR, value_reg=stored))
    consumed = emitter.load_var(CONVERT_NEXT_SOURCE_VAR)
    emitter.emit_inst(StoreVar(name=CONVERT_SOURCE_AT_VAR, value_reg=consumed))
    emitter.emit_inst(Branch(label=labels.loop))


def _code_point(emitter: HlasmEmitter, entry: CodeLabel) -> Register:
    emitter.emit_inst(Label_(label=entry))
    return emitter.load_var(CODE_POINT_VAR)


def _shifted(emitter: HlasmEmitter, value: Register, shift: int) -> Register:
    return emitter.binop(BinopKind.RSHIFT, value, emitter.int_(shift))


def _tagged(
    emitter: HlasmEmitter, value: Register, field: tuple[int, int, int]
) -> Register:
    shift, tag, mask = field
    bits = placed_bits(emitter, _shifted(emitter, value, shift), mask, 0)
    return emitter.binop(BinopKind.BIT_OR, bits, emitter.int_(tag))


def _utf8_image(emitter: HlasmEmitter, code_point: Register, width: int) -> Register:
    tag, mask = UTF8_LEADS[width]
    fields = [(CONTINUATION_SHIFT * (width - 1), tag, mask)] + [
        (CONTINUATION_SHIFT * (width - 1 - k), CONTINUATION_TAG, CONTINUATION_BITS)
        for k in range(1, width)
    ]
    units = [
        placed_bits(
            emitter,
            _tagged(emitter, code_point, field),
            BYTE_MASK,
            BITS_PER_BYTE * (width - 1 - k),
        )
        for k, field in enumerate(fields)
    ]
    return combined_bits(emitter, units)


def _utf8_width(
    emitter: HlasmEmitter,
    cursor: ConversionCursor,
    labels: ConversionLabels,
    block: tuple[CodeLabel, Register, int],
) -> None:
    label, code_point, width = block
    emitter.emit_inst(Label_(label=label))
    _store(emitter, cursor, labels, (_utf8_image(emitter, code_point, width), width))


def _utf8(
    emitter: HlasmEmitter, cursor: ConversionCursor, labels: ConversionLabels
) -> None:
    code_point = _code_point(emitter, labels.basic)
    one, two, three = (
        emitter.fresh_label(f"hl_cu_to_utf8_{width}") for width in (1, 2, 3)
    )
    emit_range_dispatch(
        emitter, code_point, [(UTF8_ONE_BYTE_END, one), (UTF8_TWO_BYTE_END, two)], three
    )
    _ = [
        _utf8_width(emitter, cursor, labels, (label, code_point, width))
        for label, width in ((one, 1), (two, 2), (three, 3))
    ]
    supplementary = _code_point(emitter, labels.supplementary)
    _store(
        emitter,
        cursor,
        labels,
        (
            _utf8_image(emitter, supplementary, UTF8_SUPPLEMENTARY),
            UTF8_SUPPLEMENTARY,
        ),
    )


def _surrogate_pair(emitter: HlasmEmitter, code_point: Register) -> Register:
    plane = emitter.binop(
        BinopKind.SUB, _shifted(emitter, code_point, HALFWORD_BITS), emitter.int_(1)
    )
    high = combined_bits(
        emitter,
        [
            emitter.int_(HIGH_SURROGATE),
            placed_bits(emitter, plane, PLANE_BITS, PLANE_SHIFT),
            placed_bits(
                emitter,
                _shifted(emitter, code_point, HIGH_PAYLOAD_SHIFT),
                HIGH_PAYLOAD_BITS,
                0,
            ),
        ],
    )
    low = combined_bits(
        emitter,
        [
            emitter.int_(LOW_SURROGATE),
            placed_bits(emitter, code_point, LOW_PAYLOAD_BITS, 0),
        ],
    )
    return combined_bits(
        emitter,
        [emitter.binop(BinopKind.LSHIFT, high, emitter.int_(HALFWORD_BITS)), low],
    )


def _utf16(
    emitter: HlasmEmitter, cursor: ConversionCursor, labels: ConversionLabels
) -> None:
    basic = _code_point(emitter, labels.basic)
    _store(emitter, cursor, labels, (basic, HALFWORD_BYTES))
    supplementary = _code_point(emitter, labels.supplementary)
    _store(
        emitter, cursor, labels, (_surrogate_pair(emitter, supplementary), WORD_BYTES)
    )


def _utf32(
    emitter: HlasmEmitter, cursor: ConversionCursor, labels: ConversionLabels
) -> None:
    emitter.emit_inst(Label_(label=labels.basic))
    emitter.emit_inst(Branch(label=labels.supplementary))
    code_point = _code_point(emitter, labels.supplementary)
    _store(emitter, cursor, labels, (code_point, WORD_BYTES))


UTF8_ENCODER: Encoder = _utf8
UTF16_ENCODER: Encoder = _utf16
UTF32_ENCODER: Encoder = _utf32
