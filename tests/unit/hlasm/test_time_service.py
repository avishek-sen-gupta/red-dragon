# pyright: standard
"""TIME's words from a TOD clock value: packed HHMMSSth, binary hundredths since midnight, and the packed 0CYYDDDF date of the Gregorian calendar."""

import pytest

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.time_service import time_words
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.straight_line_vm import register_value, run_straight_line

TOD = "%tod"
MICROSECOND_BIT = 52

CLOCKS = {
    "first_instant_of_1900": (0, (0x00000000, 0, 0x0000001F)),
    "last_hundredth_of_1900": (
        (365 * 86_400_000_000 - 1) << MICROSECOND_BIT,
        (0x23595999, 8_639_999, 0x0000365F),
    ),
    "leap_day_2000": (
        (36_583 * 86_400_000_000 + 45_296_780_000) << MICROSECOND_BIT,
        (0x12345678, 4_529_678, 0x0100060F),
    ),
    "last_day_of_2000": (
        36_889 * 86_400_000_000 << MICROSECOND_BIT,
        (0, 0, 0x0100366F),
    ),
    "fixed_clock_2023": (
        0xDE012345_6789ABCD_EF012345_00,
        (0x01112935, 428_935, 0x0123279F),
    ),
    "first_of_march_2100": (
        73_108 * 86_400_000_000 << MICROSECOND_BIT,
        (0, 0, 0x0200060F),
    ),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(CLOCKS))
def test_a_tod_value_gives_decimal_time_binary_time_and_packed_date(case: str):
    tod, expected = CLOCKS[case]
    emitter = HlasmEmitter()
    words = time_words(emitter, Register(TOD))

    vm = run_straight_line(emitter.instructions(), {TOD: tod})

    assert tuple(register_value(vm, word).value for word in words) == expected
