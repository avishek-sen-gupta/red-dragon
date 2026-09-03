"""FieldExtent alias algebra — overlap, subsumption, and the laws they obey."""

import pytest

from interpreter.cobol.field_extent import FieldExtent, Precision
from interpreter.cobol.region_id import RegionId
from tests.covers import NotLanguageFeature, covers

WS = RegionId.WORKING_STORAGE
LK = RegionId.LINKAGE


def ext(start, length, region=WS, precision=Precision.EXACT, name="F"):
    return FieldExtent(
        region=region, start=start, length=length, precision=precision, field_name=name
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_covers_its_children():
    group = ext(0, 15, name="WS-A")
    child_a = ext(0, 10, name="WS-A1")
    child_b = ext(10, 5, name="WS-A2")
    assert group.must_cover(child_a) and group.must_cover(child_b)
    assert not child_a.must_cover(group)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_adjacent_fields_do_not_overlap():
    """WS-A1 is bytes 0-9 and WS-A2 is bytes 10-14; they must not alias."""
    assert not ext(0, 10).may_alias(ext(10, 5))
    assert not ext(10, 5).may_alias(ext(0, 10))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_redefines_overlap_at_the_same_offset():
    assert ext(0, 15, name="WS-A").may_alias(ext(0, 4, name="WS-A-ALT"))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_different_regions_never_alias():
    assert not ext(0, 10, region=WS).may_alias(ext(0, 10, region=LK))
    assert not ext(0, 10, region=WS).must_cover(ext(0, 10, region=LK))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_clamped_extent_may_alias_but_never_covers():
    """A computed subscript lands SOMEWHERE in the table, so it cannot kill."""
    table = ext(20, 50, precision=Precision.CLAMPED, name="WS-TAB")
    element = ext(22, 3, name="WS-QTY")
    assert table.may_alias(element)
    assert not table.must_cover(element)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_must_cover_implies_may_alias():
    a, b = ext(0, 15), ext(0, 10)
    assert a.must_cover(b)
    assert a.may_alias(b)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_may_alias_is_symmetric():
    a, b = ext(0, 15), ext(10, 20)
    assert a.may_alias(b) == b.may_alias(a)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_zero_length_extent_aliases_nothing():
    assert not ext(0, 0).may_alias(ext(0, 10))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_alias_key_buckets_by_region():
    assert ext(0, 10, region=WS).alias_key() == ext(99, 1, region=WS).alias_key()
    assert ext(0, 10, region=WS).alias_key() != ext(0, 10, region=LK).alias_key()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_field_extent_satisfies_abstract_location():
    from interpreter.abstract_location import AbstractLocation

    assert isinstance(ext(0, 10), AbstractLocation)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_partial_overlap_may_alias_but_does_not_cover():
    """Two extents that overlap partially: neither covers the other.
    This is the case that distinguishes may from must. A partially
    overlapping write must NOT kill the definition it overlaps."""
    a = ext(0, 10)
    b = ext(5, 10)  # bytes 5..14 vs 0..9 — overlap 5..9 only
    assert a.may_alias(b) and b.may_alias(a)
    assert not a.must_cover(b)
    assert not b.must_cover(a)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_identical_extents_cover_each_other():
    a, b = ext(4, 6), ext(4, 6)
    assert a.must_cover(b) and b.must_cover(a)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_clamped_extent_does_not_cover_even_an_identical_range():
    """CLAMPED is about knowledge, not geometry: same range, still no cover."""
    clamped = ext(4, 6, precision=Precision.CLAMPED)
    exact = ext(4, 6)
    assert clamped.may_alias(exact)
    assert not clamped.must_cover(exact)
    assert exact.must_cover(clamped)
