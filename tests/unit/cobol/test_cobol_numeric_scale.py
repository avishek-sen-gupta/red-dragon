"""cobol_numeric.scale — IBM ARITH(COMPAT) places-carried rules."""

from __future__ import annotations

from cobol_numeric.scale import (
    COMPAT_DIGIT_LIMIT,
    Scale,
    add_scale,
    carry,
    div_scale,
    literal_scale,
    mul_scale,
)
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_add_scale():
    assert add_scale(Scale(3, 2), Scale(5, 0)) == Scale(6, 2)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_mul_scale():
    assert mul_scale(Scale(9, 9), Scale(9, 9)) == Scale(18, 18)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_div_scale_uses_dmax_when_larger():
    # 2023 / 4 into PIC 9(4): d = max(0 - 0, 0) = 0
    assert div_scale(Scale(4, 0), Scale(1, 0), dmax=0) == Scale(4, 0)
    # 7 / 2 into PIC 9V9: d = max(0 - 0, 1) = 1
    assert div_scale(Scale(1, 0), Scale(1, 0), dmax=1) == Scale(1, 1)
    # dividend decimals exceed divisor decimals
    assert div_scale(Scale(3, 4), Scale(2, 1), dmax=2) == Scale(4, 3)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_carry_within_limit_is_identity():
    assert carry(Scale(18, 12), dmax=2) == Scale(18, 12)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_carry_table_rows():
    assert COMPAT_DIGIT_LIMIT == 30
    # i + d > 30, d <= dmax -> 30 - d integer, d decimal
    assert carry(Scale(29, 3), dmax=3) == Scale(27, 3)
    # d > dmax, i + dmax <= 30 -> i integer, 30 - i decimal
    assert carry(Scale(18, 18), dmax=2) == Scale(18, 12)
    # d > dmax, i + dmax > 30 -> 30 - dmax integer, dmax decimal
    assert carry(Scale(29, 5), dmax=4) == Scale(26, 4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_literal_scale():
    assert literal_scale("2023") == Scale(4, 0)
    assert literal_scale("-0.007") == Scale(1, 3)
    assert literal_scale(".5") == Scale(1, 1)
