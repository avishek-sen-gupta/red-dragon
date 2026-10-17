"""Offsets, OCCURS element sizes and FD record areas computed by the ASG reader."""

from collections.abc import Sequence
from dataclasses import replace

import pytest

from cobol_asg.asg_types import CobolField
from cobol_asg.pic_parser import parse_pic
from cobol_asg.pointer_types import DOUBLEWORD_POINTER
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.storage_layout import file_section_layout, section_layout


@pytest.mark.parametrize(
    ("pic", "usage", "width"),
    [
        ("9(5)", "DISPLAY", 5),
        ("X(3)", "DISPLAY", 3),
        ("X(11)", "DISPLAY", 11),
        ("S9(5)V99", "DISPLAY", 7),
        ("9(5)", "COMP-3", 3),
        ("S9(5)V99", "COMP-3", 4),
        ("9(3)", "COMP", 2),
        ("9(5)", "COMP", 4),
        ("9(15)", "COMP", 8),
        ("S9(4)", "COMP-5", 2),
        ("S9(9)", "COMP-5", 4),
        ("9(18)", "COMP-5", 8),
        ("PPP999", "DISPLAY", 3),
        ("PPP999", "COMP-3", 2),
        ("PPP999", "COMP", 2),
        ("9(5)PP", "DISPLAY", 5),
        ("9(5)PP", "COMP-3", 3),
        ("9(5)PP", "COMP", 4),
        ("999", "DISPLAY", 3),
        ("9", "DISPLAY", 1),
        ("+99999999.99", "DISPLAY", 12),
        ("+ZZZ,ZZZ,ZZZ.99", "DISPLAY", 15),
        ("Z(9).99-", "DISPLAY", 13),
        ("-ZZZ,ZZZ,ZZZ.ZZ", "DISPLAY", 15),
        ("X(8)", "DISPLAY", 8),
        ("9(5)BB9", "DISPLAY", 8),
        ("99/99/99", "DISPLAY", 8),
        ("9(3)09", "DISPLAY", 5),
        ("$$$$.$$", "DISPLAY", 7),
        ("$(4).99", "DISPLAY", 7),
        ("++++.99", "DISPLAY", 7),
        ("PPP9", "DISPLAY", 1),
        ("9PPP", "DISPLAY", 1),
        ("S9(10)V99", "DISPLAY", 12),
        ("$$,$$$.99", "DISPLAY", 9),
        ("**,***.99", "DISPLAY", 9),
        ("*(5).99", "DISPLAY", 8),
        ("$ZZZ,ZZZ.99", "DISPLAY", 11),
        ("ZZZ.99CR", "DISPLAY", 8),
        ("ZZ9.99DB", "DISPLAY", 8),
        ("", "INDEX", 4),
        ("", "COMP-1", 4),
        ("", "COMP-2", 8),
        ("", "POINTER", 4),
    ],
)
def test_an_item_is_as_wide_as_its_picture_and_usage(
    pic: str, usage: str, width: int
) -> None:
    assert parse_pic(pic, usage).byte_length == width


def _item(name: str, pic: str = "") -> CobolField:
    return CobolField(name=name, level=5, pic=pic, usage="DISPLAY", offset=0)


def _placed(fields: Sequence[CobolField]) -> list[tuple[str, int, int]]:
    return [
        (f.name, f.offset, f.element_size)
        for top in fields
        for f in (top, *_descendants(top))
    ]


def _descendants(item: CobolField) -> list[CobolField]:
    return [d for c in item.children for d in (c, *_descendants(c))]


def test_children_follow_one_another_and_a_section_lays_its_areas_end_to_end() -> None:
    binary = CobolField(
        name="A2", level=5, pic="S9(4)", usage="COMP", offset=0, synchronized=True
    )
    table = replace(
        _item("T"),
        occurs=3,
        children=[_item("T1", "X(2)"), replace(_item("T2", "9(3)"), redefines="T1")],
    )
    group = CobolField(
        name="G",
        level=1,
        pic="",
        usage="DISPLAY",
        offset=0,
        children=[
            _item("A1", "X"),
            binary,
            replace(_item("A3", "S9(3)"), sign_leading=True, sign_separate=True),
            table,
            replace(_item("A4", "X"), redefines="A1"),
            replace(_item("REN"), renames_from=RefModOperand(name="A1")),
        ],
    )
    longer = CobolField(
        name="L", level=1, pic="X(30)", usage="DISPLAY", offset=0, redefines="G"
    )
    after = CobolField(name="N", level=77, pic="9(4)", usage="COMP", offset=0)

    assert _placed(section_layout([group, longer, after])) == [
        ("G", 0, 0),
        ("A1", 0, 0),
        ("A2", 2, 0),
        ("A3", 4, 0),
        ("T", 8, 2),
        ("T1", 0, 0),
        ("T2", 0, 0),
        ("A4", 0, 0),
        ("REN", 0, 0),
        ("L", 13, 0),
        ("N", 30, 0),
    ]


def test_records_of_one_fd_share_its_area_and_the_next_fd_follows() -> None:
    first = [
        CobolField(name="R1", level=1, pic="X(10)", usage="DISPLAY", offset=0),
        CobolField(
            name="R2",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            children=[_item("R2A", "X(4)"), _item("R2B", "X(8)")],
        ),
    ]
    second = [CobolField(name="S1", level=1, pic="X(7)", usage="DISPLAY", offset=0)]

    assert _placed(file_section_layout([first, second])) == [
        ("R1", 0, 0),
        ("R2", 0, 0),
        ("R2A", 0, 0),
        ("R2B", 4, 0),
        ("S1", 12, 0),
    ]


def test_a_pointer_is_as_wide_as_the_addressing_mode_says() -> None:
    pointer = CobolField(
        name="P",
        level=1,
        pic="",
        usage="POINTER",
        offset=0,
        pointer_type=DOUBLEWORD_POINTER,
    )
    after = CobolField(name="Q", level=1, pic="X", usage="DISPLAY", offset=0)

    assert _placed(section_layout([pointer, after])) == [("P", 0, 0), ("Q", 8, 0)]
