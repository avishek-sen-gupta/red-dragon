# pyright: standard
"""The Unicode conversions' source readers: each reads the next UTF-8, UTF-16 or UTF-32 character, stops at an exhausted operand or an invalid character, and leaves its code point and the offset after it for the encoder."""

from collections.abc import Callable, Mapping, Sequence

from interpreter.hlasm.bit_fields import combined_bits, placed_bits
from interpreter.hlasm.conversion_cursor import ConversionCursor
from interpreter.hlasm.conversion_labels import ConversionLabels
from interpreter.hlasm.hlasm_constants import (
    CODE_POINT_VAR,
    CONVERT_NEXT_SOURCE_VAR,
    HALFWORD_BYTES,
    ONE_BYTE,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.range_dispatch import emit_range_dispatch
from interpreter.hlasm.unit_value import unit_value
from interpreter.instructions import Branch, BranchIf, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Decoder = Callable[[HlasmEmitter, ConversionCursor, ConversionLabels], None]
type ValueCheck = tuple[int, BinopKind, int]

ALL_BITS = 0x1FFFFF
CONTINUATION_TAG_BITS = 0xC0
CONTINUATION_TAG = 0x80
CONTINUATION_BITS = 0x3F
CONTINUATION_SHIFT = 6
UTF8_LEADS_UNCHECKED = (0x80, 0xC0, 0xE0, 0xF0, 0xF8)
UTF8_LEADS_CHECKED = (0x80, 0xC2, 0xE0, 0xF0, 0xF5)
UTF8_LEAD_BITS: Mapping[int, int] = {2: 0x1F, 3: 0x0F, 4: 0x07}
SUPPLEMENTARY_UTF8_BYTES = 4
SURROGATE_BITS = 0xF800
HIGH_SURROGATE = 0xD800
LOW_SURROGATE = 0xDC00
SURROGATES_END = 0xE000
LOW_SURROGATE_TAG_BITS = 0xFC00
SURROGATE_PAYLOAD = 0x3FF
SURROGATE_PAYLOAD_BITS = 10
SUPPLEMENTARY = 0x10000
UNICODE_END = 0x110000
UTF8_CHECKED_VALUES: Mapping[int, tuple[ValueCheck, ...]] = {
    2: (),
    3: (
        (ALL_BITS, BinopKind.LT, 0x800),
        (SURROGATE_BITS, BinopKind.EQ, HIGH_SURROGATE),
    ),
    4: (
        (ALL_BITS, BinopKind.LT, SUPPLEMENTARY),
        (ALL_BITS, BinopKind.GE, UNICODE_END),
    ),
}


def _read(
    emitter: HlasmEmitter, cursor: ConversionCursor, offset: int, width: int
) -> Register:
    at = emitter.binop(BinopKind.ADD, cursor.source_at, emitter.int_(offset))
    return unit_value(emitter, width)(emitter.load_bytes(cursor.source, at, width))


def _goto_if(emitter: HlasmEmitter, condition: Register, target: CodeLabel) -> None:
    more = emitter.fresh_label("hl_cu_more")
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(target, more)))
    emitter.emit_inst(Label_(label=more))


def _require(
    emitter: HlasmEmitter, cursor: ConversionCursor, width: int, exhausted: CodeLabel
) -> None:
    short = emitter.binop(BinopKind.LT, cursor.source_left, emitter.int_(width))
    _goto_if(emitter, short, exhausted)


def _reject(
    emitter: HlasmEmitter, value: Register, check: ValueCheck, invalid: CodeLabel
) -> None:
    mask, comparison, bound = check
    masked = emitter.binop(BinopKind.BIT_AND, value, emitter.int_(mask))
    _goto_if(emitter, emitter.binop(comparison, masked, emitter.int_(bound)), invalid)


def _reject_all(
    emitter: HlasmEmitter,
    checks: Sequence[tuple[Register, ValueCheck]],
    invalid: CodeLabel,
) -> None:
    _ = [_reject(emitter, value, check, invalid) for value, check in checks]


def _hold(
    emitter: HlasmEmitter, cursor: ConversionCursor, character: tuple[Register, int]
) -> None:
    code_point, width = character
    after = emitter.binop(BinopKind.ADD, cursor.source_at, emitter.int_(width))
    emitter.emit_inst(StoreVar(name=CODE_POINT_VAR, value_reg=code_point))
    emitter.emit_inst(StoreVar(name=CONVERT_NEXT_SOURCE_VAR, value_reg=after))


def _decoded(
    emitter: HlasmEmitter,
    cursor: ConversionCursor,
    character: tuple[Register, int],
    entry: CodeLabel,
) -> None:
    _hold(emitter, cursor, character)
    emitter.emit_inst(Branch(label=entry))


def _utf8_code_point(
    emitter: HlasmEmitter, lead: Register, continuations: Sequence[Register]
) -> Register:
    count = len(continuations)
    payloads = [
        placed_bits(
            emitter,
            byte,
            CONTINUATION_BITS,
            CONTINUATION_SHIFT * (count - 1 - index),
        )
        for index, byte in enumerate(continuations)
    ]
    first = placed_bits(
        emitter, lead, UTF8_LEAD_BITS[count + 1], CONTINUATION_SHIFT * count
    )
    return combined_bits(emitter, [first, *payloads])


def _utf8_multibyte(
    emitter: HlasmEmitter,
    cursor: ConversionCursor,
    labels: ConversionLabels,
    unit: tuple[Register, int, bool],
) -> None:
    lead, width, checked = unit
    _require(emitter, cursor, width, labels.exhausted)
    continuations = [_read(emitter, cursor, k, ONE_BYTE) for k in range(1, width)]
    tag_checks = (
        ((CONTINUATION_TAG_BITS, BinopKind.NE, CONTINUATION_TAG),) if checked else ()
    )
    _reject_all(
        emitter,
        [(byte, check) for byte in continuations for check in tag_checks],
        labels.invalid,
    )
    code_point = _utf8_code_point(emitter, lead, continuations)
    value_checks = UTF8_CHECKED_VALUES[width] if checked else ()
    _reject_all(
        emitter, [(code_point, check) for check in value_checks], labels.invalid
    )
    entry = labels.supplementary if width == SUPPLEMENTARY_UTF8_BYTES else labels.basic
    _decoded(emitter, cursor, (code_point, width), entry)


def _utf8(checked: bool) -> Decoder:
    leads = UTF8_LEADS_CHECKED if checked else UTF8_LEADS_UNCHECKED

    def decode(
        emitter: HlasmEmitter, cursor: ConversionCursor, labels: ConversionLabels
    ) -> None:
        _require(emitter, cursor, ONE_BYTE, labels.exhausted)
        lead = _read(emitter, cursor, 0, ONE_BYTE)
        one, two, three, four = (
            emitter.fresh_label(f"hl_cu_utf8_{width}") for width in range(1, 5)
        )
        bounds = (one, labels.invalid, two, three, four)
        emit_range_dispatch(
            emitter, lead, list(zip(leads, bounds, strict=True)), labels.invalid
        )
        emitter.emit_inst(Label_(label=one))
        _decoded(emitter, cursor, (lead, ONE_BYTE), labels.basic)
        _ = [
            _utf8_label(emitter, cursor, labels, (label, lead, width, checked))
            for width, label in ((2, two), (3, three), (4, four))
        ]

    return decode


def _utf8_label(
    emitter: HlasmEmitter,
    cursor: ConversionCursor,
    labels: ConversionLabels,
    block: tuple[CodeLabel, Register, int, bool],
) -> None:
    label, lead, width, checked = block
    emitter.emit_inst(Label_(label=label))
    _utf8_multibyte(emitter, cursor, labels, (lead, width, checked))


def _surrogate_pair(
    emitter: HlasmEmitter,
    cursor: ConversionCursor,
    labels: ConversionLabels,
    unit: tuple[Register, bool],
) -> None:
    high, checked = unit
    _require(emitter, cursor, 2 * HALFWORD_BYTES, labels.exhausted)
    low = _read(emitter, cursor, HALFWORD_BYTES, HALFWORD_BYTES)
    tag_checks = (
        ((LOW_SURROGATE_TAG_BITS, BinopKind.NE, LOW_SURROGATE),) if checked else ()
    )
    _reject_all(emitter, [(low, check) for check in tag_checks], labels.invalid)
    payloads = combined_bits(
        emitter,
        [
            placed_bits(emitter, high, SURROGATE_PAYLOAD, SURROGATE_PAYLOAD_BITS),
            placed_bits(emitter, low, SURROGATE_PAYLOAD, 0),
        ],
    )
    code_point = emitter.binop(BinopKind.ADD, payloads, emitter.int_(SUPPLEMENTARY))
    _decoded(emitter, cursor, (code_point, 2 * HALFWORD_BYTES), labels.supplementary)


def _utf16(checked: bool) -> Decoder:
    def decode(
        emitter: HlasmEmitter, cursor: ConversionCursor, labels: ConversionLabels
    ) -> None:
        _require(emitter, cursor, HALFWORD_BYTES, labels.exhausted)
        unit = _read(emitter, cursor, 0, HALFWORD_BYTES)
        single, pair = emitter.fresh_label("hl_cu_utf16_single"), emitter.fresh_label(
            "hl_cu_utf16_pair"
        )
        isolated_low = labels.invalid if checked else single
        emit_range_dispatch(
            emitter,
            unit,
            [
                (HIGH_SURROGATE, single),
                (LOW_SURROGATE, pair),
                (SURROGATES_END, isolated_low),
            ],
            single,
        )
        emitter.emit_inst(Label_(label=single))
        _decoded(emitter, cursor, (unit, HALFWORD_BYTES), labels.basic)
        emitter.emit_inst(Label_(label=pair))
        _surrogate_pair(emitter, cursor, labels, (unit, checked))

    return decode


def _utf32(
    emitter: HlasmEmitter, cursor: ConversionCursor, labels: ConversionLabels
) -> None:
    _require(emitter, cursor, WORD_BYTES, labels.exhausted)
    code_point = _read(emitter, cursor, 0, WORD_BYTES)
    _hold(emitter, cursor, (code_point, WORD_BYTES))
    emit_range_dispatch(
        emitter,
        code_point,
        [
            (HIGH_SURROGATE, labels.basic),
            (SURROGATES_END, labels.invalid),
            (SUPPLEMENTARY, labels.basic),
            (UNICODE_END, labels.supplementary),
        ],
        labels.invalid,
    )


UTF8_DECODERS: tuple[Decoder, Decoder] = (_utf8(False), _utf8(True))
UTF16_DECODERS: tuple[Decoder, Decoder] = (_utf16(False), _utf16(True))
UTF32_DECODERS: tuple[Decoder, Decoder] = (_utf32, _utf32)
