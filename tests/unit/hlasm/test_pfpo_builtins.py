# pyright: standard
"""The PFPO builtin reads its formats and controls from GR0's word, maps each family's fields to values and back, drops the inexact and quantum conditions its controls suppress, and returns the scaling exponent as a 32-bit word."""

from collections.abc import Sequence

from interpreter.hlasm.pfpo_builtins import pfpo_builtins
from interpreter.hlasm.pfpo_formats import PFPO_BUILTIN
from interpreter.types.typed_value import typed
from interpreter.vm.vm import VMState
from tests.covers import NotLanguageFeature, covers

NEAREST_EVEN = 8
BFP_TENTH = [0, 1019, 0x999999999999A]


def _call(word: int, mode: int, fields: Sequence[int]) -> int | list[int]:
    builtin = pfpo_builtins()[PFPO_BUILTIN]
    return builtin([typed(word), typed(mode), typed(list(fields))], VMState()).value


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_pfpo_converts_between_the_word_s_formats_under_its_controls():
    assert {
        "bfp long to dfp long": _call(0x01090600, NEAREST_EVEN, BFP_TENTH),
        "inexact suppressed": _call(0x01090680, NEAREST_EVEN, BFP_TENTH),
        "quantum permitted": _call(0x01090620, NEAREST_EVEN, BFP_TENTH),
        "dfp long to hfp short": _call(0x01000900, NEAREST_EVEN, [1, 398, 15]),
        "hfp short to bfp short": _call(0x01050000, NEAREST_EVEN, [0, 0x41, 0x100000]),
        "underflow scaled": _call(0x01050900, NEAREST_EVEN, [1, 0, 1]),
    } == {
        "bfp long to dfp long": [
            0,
            382,
            10**15,
            0,
            382,
            10**15,
            0x08,
            0x08,
            0,
            0x08,
            0,
        ],
        "inexact suppressed": [0, 382, 10**15, 0, 382, 10**15, 0, 0, 0, 0, 0],
        "quantum permitted": [0, 382, 10**15, 0, 382, 10**15, 0x0C, 0x0C, 0, 0x08, 0],
        "dfp long to hfp short": [1, 0x41, 0xF00000, 1, 0x41, 0xF00000, 0, 0, 0, 0, 0],
        "hfp short to bfp short": [0, 127, 0, 0, 127, 0, 0, 0, 0, 0, 0],
        "underflow scaled": [
            *[1, 0, 0],
            *[1, 127, 0x6A5DA5],
            *[0x18, 0x18, 0x1C, 0x08],
            0xFFFFFAD5,
        ],
    }
