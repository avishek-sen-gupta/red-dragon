# pyright: standard
"""GETMAIN, FREEMAIN, STORAGE and TIME in RedDragon, with our macros, and in z390, with its own: addresses differ, so the programs compare what follows from them (alignment, distinct areas, data read back, return codes); z390's time is its wall clock, so TIME compares the shape of the words."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import storage_service_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
Z390_SETS_R15_ON_SVC_10 = {6: 0, 10: 0}
Z390_R15 = {
    "getmain_r": Z390_SETS_R15_ON_SVC_10,
    "getmain_r_rounds_the_length": Z390_SETS_R15_ON_SVC_10,
}
CENTURY_2000 = 0x01
DATE_SIGN = 0xF


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.PAIR_CASES))
def test_obtained_areas_match(z390: Z390Runner, tmp_path: Path, case: str):
    source, expected = programs.PAIR_CASES[case]

    ours = run_hlasm_machine(source)
    theirs = z390.run_machine(source, tmp_path)

    assert (
        (ours.run, programs.pair_view(ours.gprs)),
        (theirs.run, programs.pair_view(theirs.gprs)),
    ) == (
        (ABENDED, expected),
        (ABENDED, {**expected, **Z390_R15.get(case, {})}),
    )


def _digits(word: int, count: int) -> list[int]:
    return [(word >> (4 * i)) & 0xF for i in reversed(range(count))]


def _number(digits: Sequence[int]) -> int:
    return sum(d * 10**i for i, d in enumerate(reversed(digits)))


def _hundredths(dec: int) -> int:
    d = _digits(dec, 8)
    return (
        _number(d[0:2]) * 360_000
        + _number(d[2:4]) * 6_000
        + _number(d[4:6]) * 100
        + _number(d[6:8])
    )


def _valid_time(dec: int) -> bool:
    d = _digits(dec, 8)
    return (
        all(x <= 9 for x in d)
        and _number(d[0:2]) < 24
        and _number(d[2:4]) < 60
        and _number(d[4:6]) < 60
    )


def _valid_date(date: int) -> bool:
    d = _digits(date >> 4, 7)
    return all(x <= 9 for x in d) and 1 <= _number(d[4:7]) <= 366


type TimeShape = tuple[bool, bool, int, int, bool, bool, int]


def _time_shape(gprs: Mapping[int, int]) -> TimeShape:
    words = programs.time_view(gprs)
    dec, date, binary = words[2], words[3], words[4]
    return (
        _valid_time(dec) and _valid_time(words[7]),
        _valid_date(date),
        date >> 24,
        date & 0xF,
        0 <= binary - _hundredths(dec) < 100,
        words[5] == date,
        words[6],
    )


SHAPE: TimeShape = (True, True, CENTURY_2000, DATE_SIGN, True, True, 0)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_time_words_have_the_same_shape(z390: Z390Runner, tmp_path: Path):
    ours = run_hlasm_machine(programs.TIME)
    theirs = z390.run_machine(programs.TIME, tmp_path)

    assert (
        (ours.run, _time_shape(ours.gprs)),
        (theirs.run, _time_shape(theirs.gprs)),
    ) == ((ABENDED, SHAPE), (ABENDED, SHAPE))
