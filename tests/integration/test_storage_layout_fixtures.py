"""Offsets the ASG reader computes for the bridge's layout fixtures, parsed end to end."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from cobol_asg.asg_types import CobolASG, CobolField
from interpreter.frontend import make_cobol_parser
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401

pytestmark = pytest.mark.usefixtures("bridge_jar")

_FIXTURES = (
    Path(__file__).resolve().parents[2] / "proleap-bridge/src/test/resources/fixtures"
)


def _parsed(fixture: str) -> CobolASG:
    return make_cobol_parser().parse((_FIXTURES / fixture).read_bytes()).first_program


def _placed(fields: Sequence[CobolField]) -> list[tuple[str, int]]:
    return [(f.name, f.offset) for f in fields]


def _every(fields: Sequence[CobolField]) -> list[CobolField]:
    return [d for f in fields for d in (f, *_every(f.children))]


def _named(fields: Sequence[CobolField], name: str) -> CobolField:
    return next(f for f in _every(fields) if f.name == name)


def test_edited_fields_get_contiguous_non_overlapping_offsets():
    children = _parsed("EditWidths.cbl").data_fields[0].children

    assert [c.offset for c in children[:8]] == [0, 8, 12, 20, 24, 29, 33, 40]


def test_records_of_one_fd_share_its_area_and_fds_do_not_overlap():
    asg = _parsed("file_record_areas.cbl")

    assert [
        (asg.file_record_to_select[r.name.upper()], r.name, r.offset)
        for r in asg.file_fields
    ] == [
        ("PRINT-FILE", "PRINT-REC", 0),
        ("PRINT-FILE", "DUMMY-RECORD", 0),
        ("PRINT-FILE", "SHORT-REC", 0),
        ("DATA-FILE", "DATA-REC", 12),
        ("DATA-FILE", "DATA-ALT", 12),
    ]
    assert asg.file_fields[0].children[1].offset == 4


def test_floating_point_items_occupy_four_and_eight_bytes_without_a_picture():
    assert _placed(_parsed("float_items.cbl").data_fields) == [
        ("G", 0),
        ("H", 8),
        ("GRP", 12),
        ("F1", 24),
    ]


def test_signed_display_items_take_the_nearest_sign_clause_and_others_take_none():
    fields = _parsed("group_sign.cbl").data_fields

    assert [
        (name, _named(fields, name).sign_leading, _named(fields, name).sign_separate)
        for name in "ABCDE"
    ] == [
        ("A", False, True),
        ("B", True, True),
        ("C", False, False),
        ("D", False, False),
        ("E", False, False),
    ]
    assert (_named(fields, "C").offset, _named(fields, "E").offset) == (3, 7)
