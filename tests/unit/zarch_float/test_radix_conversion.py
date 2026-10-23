# pyright: standard
"""PFPO radix conversion: the preferred quantum of figure 9-29, rounding into each radix, NaN payloads and specials, HFP overflow and underflow under their controls, and the scaled value with its scaling exponent (PoO 9-35 to 9-46)."""

from collections.abc import Sequence

from tests.covers import NotLanguageFeature, covers
from tests.unit.zarch_float.bfp_bits import long_of, to_bits
from tests.unit.zarch_float.hfp_bits import image, short
from zarch_float.bfp_format import LONG as BFP_LONG
from zarch_float.bfp_format import SHORT as BFP_SHORT
from zarch_float.bfp_value import BfpValue
from zarch_float.condition import Condition
from zarch_float.dfp_format import LONG as DFP_LONG
from zarch_float.dfp_format import SHORT as DFP_SHORT
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind
from zarch_float.hfp_format import SHORT as HFP_SHORT
from zarch_float.hfp_value import HfpValue
from zarch_float.radix_controls import RadixControls
from zarch_float.radix_conversion import convert_radix
from zarch_float.radix_result import FloatValue, RadixResult
from zarch_float.rounding_mode import RoundingMode

NE = RoundingMode.NEAREST_EVEN
PLAIN = RadixControls(False, False, False)
QUANTUM_OF_ONE = RadixControls(False, False, True)
REPORTED = RadixControls(True, True, False)
INEXACT = frozenset({Condition.INEXACT})
INCREMENTED = frozenset({Condition.INEXACT, Condition.INCREMENTED})
INVALID = frozenset({Condition.INVALID})


def _dfp(result: RadixResult) -> tuple[int, int]:
    value = result.value
    assert isinstance(value, DfpValue)
    return value.significand, value.exponent


def _bfp_bits(value: FloatValue) -> int:
    assert isinstance(value, BfpValue)
    return to_bits(value)


def _hfp_image(value: FloatValue) -> int:
    assert isinstance(value, HfpValue)
    return image(value)


FIGURE_9_29: Sequence[tuple[float, tuple[int, int], tuple[int, int]]] = (
    (0.0, (0, 90), (0, 0)),
    (0.125, (125, -3), (125, -3)),
    (1.0, (1, 0), (1, 0)),
    (10.0, (1, 1), (10, 0)),
    (100.0, (1, 2), (100, 0)),
    (1000.0, (1, 3), (1000, 0)),
    (9999.0, (9999, 0), (9999, 0)),
    (10000.0, (1, 4), (10000, 0)),
    (10001.0, (10001, 0), (10001, 0)),
    (1e5, (1, 5), (100000, 0)),
    (1e6, (1, 6), (1000000, 0)),
    (1e10, (1, 10), (1000000, 4)),
    (1e15, (1, 15), (1000000, 9)),
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_exact_dfp_results_take_the_quantum_figure_9_29_gives():
    results = [
        (
            convert_radix(long_of(x), DFP_SHORT, NE, PLAIN),
            convert_radix(long_of(x), DFP_SHORT, NE, QUANTUM_OF_ONE),
        )
        for x, largest, closest in FIGURE_9_29
    ]

    assert [(_dfp(a), _dfp(b)) for a, b in results] == [
        (largest, closest) for x, largest, closest in FIGURE_9_29
    ]
    assert [a.conditions for a, b in results] == [frozenset()] * 13
    assert [Condition.QUANTUM in b.conditions for a, b in results] == [
        closest[1] > 0 for x, largest, closest in FIGURE_9_29
    ]
    assert convert_radix(long_of(0.1), DFP_SHORT, NE, PLAIN).value == DfpValue(
        DFP_SHORT, False, FloatKind.FINITE, 1000000, -7
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_values_round_once_into_each_radix():
    tenth = DfpValue(DFP_LONG, False, FloatKind.FINITE, 1, -1)

    assert {
        "dfp 0.1 to bfp long": _bfp_bits(
            convert_radix(tenth, BFP_LONG, NE, PLAIN).value
        ),
        "bfp 0.1 to hfp short": _hfp_image(
            convert_radix(long_of(0.1), HFP_SHORT, NE, PLAIN).value
        ),
        "bfp -1 to hfp short": _hfp_image(
            convert_radix(long_of(-1.0), HFP_SHORT, NE, PLAIN).value
        ),
        "hfp 1 to dfp long": convert_radix(
            short(0x41100000), DFP_LONG, NE, PLAIN
        ).value,
    } == {
        "dfp 0.1 to bfp long": 0x3FB99999_9999999A,
        "bfp 0.1 to hfp short": 0x4019999A,
        "bfp -1 to hfp short": 0xC1100000,
        "hfp 1 to dfp long": DfpValue(DFP_LONG, False, FloatKind.FINITE, 1, 0),
    }
    assert convert_radix(tenth, BFP_LONG, NE, PLAIN).conditions == INCREMENTED


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_specials_keep_their_payloads_or_become_hmax():
    snan = BfpValue(BFP_LONG, True, FloatKind.SNAN, 7)
    big_payload = DfpValue(DFP_LONG, False, FloatKind.QNAN, 10**12)
    infinity = DfpValue(DFP_LONG, True, FloatKind.INFINITY)

    assert {
        "snan to dfp": convert_radix(snan, DFP_LONG, NE, PLAIN),
        "payload too big for bfp short": convert_radix(
            big_payload, BFP_SHORT, NE, PLAIN
        ),
        "nan to hfp": convert_radix(snan, HFP_SHORT, NE, PLAIN),
        "infinity to hfp": convert_radix(infinity, HFP_SHORT, NE, PLAIN),
    } == {
        "snan to dfp": RadixResult(
            DfpValue(DFP_LONG, True, FloatKind.QNAN, 7),
            INVALID,
            DfpValue(DFP_LONG, True, FloatKind.QNAN, 7),
            frozenset(),
            0,
        ),
        "payload too big for bfp short": RadixResult(
            BfpValue(BFP_SHORT, False, FloatKind.QNAN, 0),
            frozenset(),
            BfpValue(BFP_SHORT, False, FloatKind.QNAN, 0),
            frozenset(),
            0,
        ),
        "nan to hfp": RadixResult(
            HfpValue(HFP_SHORT, False, 0xFFFFFF, 63),
            INVALID,
            HfpValue(HFP_SHORT, False, 0xFFFFFF, 63),
            frozenset(),
            0,
        ),
        "infinity to hfp": RadixResult(
            HfpValue(HFP_SHORT, True, 0xFFFFFF, 63),
            INVALID,
            HfpValue(HFP_SHORT, True, 0xFFFFFF, 63),
            frozenset(),
            0,
        ),
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_hfp_out_of_range_results_follow_the_controls():
    huge = DfpValue(DFP_LONG, False, FloatKind.FINITE, 1, 80)
    tiny = DfpValue(DFP_LONG, True, FloatKind.FINITE, 1, -80)
    hmax = HfpValue(HFP_SHORT, False, 0xFFFFFF, 63)

    assert {
        "hfp overflow as invalid": convert_radix(huge, HFP_SHORT, NE, PLAIN).conditions,
        "hfp underflow unreported": convert_radix(
            tiny, HFP_SHORT, NE, PLAIN
        ).conditions,
        "hfp overflow reported": convert_radix(
            huge, HFP_SHORT, NE, REPORTED
        ).conditions,
        "hfp underflow reported": convert_radix(
            tiny, HFP_SHORT, NE, REPORTED
        ).conditions,
    } == {
        "hfp overflow as invalid": INVALID,
        "hfp underflow unreported": INEXACT,
        "hfp overflow reported": frozenset({Condition.OVERFLOW, Condition.INEXACT}),
        "hfp underflow reported": frozenset(
            {Condition.TINY, Condition.UNDERFLOW, Condition.INEXACT}
        ),
    }
    assert convert_radix(huge, HFP_SHORT, NE, PLAIN).value == hmax
    assert convert_radix(tiny, HFP_SHORT, NE, PLAIN).value == HfpValue(
        HFP_SHORT, True, 0, -64
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_trapped_result_scales_into_one_to_the_radix_with_its_exponent():
    huge = DfpValue(DFP_LONG, False, FloatKind.FINITE, 1, 80)
    to_hfp = convert_radix(huge, HFP_SHORT, NE, REPORTED)
    to_bfp = convert_radix(
        DfpValue(DFP_LONG, False, FloatKind.FINITE, 1, 39), BFP_SHORT, NE, PLAIN
    )
    to_dfp = convert_radix(long_of(1e300), DFP_SHORT, NE, PLAIN)

    assert (
        _hfp_image(to_hfp.scaled),
        to_hfp.scaling,
    ) == (0x4135F9DF, 66)
    assert (to_bfp.value, _bfp_bits(to_bfp.scaled), to_bfp.scaling) == (
        BfpValue(BFP_SHORT, False, FloatKind.INFINITY),
        0x3FBC1440,
        129,
    )
    assert (to_dfp.scaled, to_dfp.scaling, to_dfp.conditions) == (
        DfpValue(DFP_SHORT, False, FloatKind.FINITE, 1000000, -6),
        300,
        frozenset(
            {
                Condition.OVERFLOW,
                Condition.INEXACT,
                Condition.INCREMENTED,
                Condition.QUANTUM,
            }
        ),
    )
