"""Class conditions in IR: IS NUMERIC on a zoned or packed decimal item's stored bytes and on character data, and IS class-name."""

from __future__ import annotations

from collections.abc import Sequence
from functools import reduce

from cobol_asg.cobol_types import CobolTypeDescriptor
from interpreter.cobol.cobol_constants import BuiltinName, NibblePosition
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName

_DIGIT_CHARACTERS = "0123456789"
_HIGHEST_DIGIT = 9
_UNSIGNED_ZONE = 0xF
_SIGNED_ZONES = (0xC, 0xD, 0xF)
_SEPARATE_SIGNS = (0x4E, 0x60)


def emit_zoned_is_numeric(
    e: IrEmitter, stored: Register, td: CobolTypeDescriptor, length: int, sign_at: int
) -> Register:
    bytes_ = [e.call(BuiltinName.LIST_GET, stored, e.int_(i)) for i in range(length)]
    sign_byte = bytes_[sign_at]
    sign_valid = (
        _any_equal(e, sign_byte, _SEPARATE_SIGNS)
        if td.sign_separate
        else e.binop(
            "and",
            _any_equal(e, _nibble(e, sign_byte, NibblePosition.HIGH), _zones(td)),
            _is_digit(e, _nibble(e, sign_byte, NibblePosition.LOW)),
        )
    )
    return _all(
        e,
        [
            sign_valid,
            *(_is_zoned_digit(e, b) for i, b in enumerate(bytes_) if i != sign_at),
        ],
    )


def emit_packed_is_numeric(
    e: IrEmitter, stored: Register, td: CobolTypeDescriptor, length: int
) -> Register:
    nibbles = [
        _nibble(e, byte, position)
        for byte in (
            e.call(BuiltinName.LIST_GET, stored, e.int_(i)) for i in range(length)
        )
        for position in (NibblePosition.HIGH, NibblePosition.LOW)
    ]
    return _all(
        e,
        [
            _any_equal(e, nibbles[-1], _zones(td)),
            *(_is_digit(e, nibble) for nibble in nibbles[:-1]),
        ],
    )


def emit_is_digits(e: IrEmitter, text: Register) -> Register:
    return e.binop(
        "and",
        e.binop(">", e.call(BuiltinName.LENGTH, text), e.int_(0)),
        emit_all_characters_in(e, text, e.text(_DIGIT_CHARACTERS)),
    )


def emit_all_characters_in(
    e: IrEmitter, text: Register, characters: Register
) -> Register:
    length = e.call(BuiltinName.LENGTH, text)
    position = e.var("class_position", e.int_(0))
    within = e.var("class_within", e.bool_(True))

    e.loop(
        "class_scan",
        lambda _head, done: _scan_one(
            e, (text, characters, length), (position, within), done
        ),
    )
    return e.load(within)


def _scan_one(
    e: IrEmitter,
    operands: tuple[Register, Register, Register],
    cursor: tuple[VarName, VarName],
    done: CodeLabel,
) -> None:
    text, characters, length = operands
    position, within = cursor
    more = e.label("class_more")
    e.branch_if(e.binop("<", e.load(position), length), more, done)
    e.place(more)
    found = e.call(
        BuiltinName.STRING_FIND,
        characters,
        e.call(BuiltinName.STRING_SLICE, text, e.load(position), e.int_(1)),
    )
    e.store(within, e.binop(">=", found, e.int_(0)))
    e.skip_if(e.binop("<", found, e.int_(0)), done)
    e.store(position, e.binop("+", e.load(position), e.int_(1)))


def _zones(td: CobolTypeDescriptor) -> tuple[int, ...]:
    return _SIGNED_ZONES if td.signed else (_UNSIGNED_ZONE,)


def _nibble(e: IrEmitter, byte: Register, position: NibblePosition) -> Register:
    return e.call(BuiltinName.NIBBLE_GET, byte, e.text(position.value))


def _is_digit(e: IrEmitter, nibble: Register) -> Register:
    return e.binop("<=", nibble, e.int_(_HIGHEST_DIGIT))


def _is_zoned_digit(e: IrEmitter, byte: Register) -> Register:
    return e.binop(
        "and",
        e.binop(">=", byte, e.int_(_UNSIGNED_ZONE << 4)),
        e.binop("<=", byte, e.int_((_UNSIGNED_ZONE << 4) | _HIGHEST_DIGIT)),
    )


def _any_equal(e: IrEmitter, value: Register, options: Sequence[int]) -> Register:
    return reduce(
        lambda found, option: e.binop(
            "or", found, e.binop("==", value, e.int_(option))
        ),
        options[1:],
        e.binop("==", value, e.int_(options[0])),
    )


def _all(e: IrEmitter, tests: Sequence[Register]) -> Register:
    return reduce(lambda held, test: e.binop("and", held, test), tests[1:], tests[0])
