# pyright: standard
"""Decimal lanes in IR: an integer spreads one digit per packed or zoned lane, lanes combine back into the integer whatever sits above each digit, and a digit above 9 in any lane is caught."""

from collections.abc import Callable, Sequence

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.decimal_lanes import (
    combined_digits,
    invalid_digits,
    spread_digits,
)
from interpreter.instructions import Return_
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.straight_line_vm import returned_value

type Builder = Callable[[HlasmEmitter, Sequence[Register]], Register]

DIGITS = int("1234567890" * 3 + "1234")
PACKED = int(str(DIGITS), 16)
ZONED = int("".join(f"F{digit}" for digit in str(DIGITS)), 16)


def _run(builder: Builder, argument: int) -> int:
    emitter = HlasmEmitter()
    emitter.emit_inst(Return_(value_reg=builder(emitter, [Register("%p0")])))
    value = returned_value(emitter.instructions(), {"%p0": argument})
    assert isinstance(value, int)
    return value


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_digits_spread_into_lanes_and_combine_back():
    assert {
        "packed 34": _run(spread_digits(4, 34).body, DIGITS),
        "packed 16 of 16": _run(spread_digits(4, 16).body, 9876543210123456),
        "zoned 34": _run(spread_digits(8, 34).body, DIGITS),
        "value of packed": _run(combined_digits(4, 36).body, PACKED),
        "value of zoned": _run(combined_digits(8, 34).body, ZONED),
        "value of character zones": _run(combined_digits(8, 16).body, 0x3132),
        "value of an odd lane count": _run(combined_digits(4, 18).body, 0x123456789),
    } == {
        "packed 34": PACKED,
        "packed 16 of 16": 0x9876543210123456,
        "zoned 34": ZONED & int("0F" * 34, 16),
        "value of packed": DIGITS,
        "value of zoned": DIGITS,
        "value of character zones": 12,
        "value of an odd lane count": 123456789,
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_digit_above_nine_is_caught_in_any_lane():
    def caught(lane_bits: int, count: int, image: int) -> int:
        return _run(
            lambda emitter, p: invalid_digits(emitter, p[0], lane_bits, count), image
        )

    assert [
        caught(4, 36, digit << 4 * at) for at in range(36) for digit in range(16)
    ] == [int(digit > 9) for _ in range(36) for digit in range(16)]
    assert [
        caught(8, 34, (0xF0 | digit) << 8 * at)
        for at in range(34)
        for digit in range(16)
    ] == [int(digit > 9) for _ in range(34) for digit in range(16)]
    assert caught(4, 36, PACKED) == 0
    assert caught(8, 34, ZONED) == 0
