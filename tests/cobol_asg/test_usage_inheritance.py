"""A group's USAGE applies to each item in it; an item's own USAGE wins."""

from cobol_asg.cobol_field import CobolField
from cobol_asg.storage_layout import byte_length


def _entry(name: str, pic: str = "", **clauses: str | dict | list) -> dict:
    return {"name": name, "level": 5, "pic": pic} | clauses


_GROUP = _entry(
    "OUTER",
    usage="COMP",
    sign={"position": "LEADING", "separate": True},
    children=[
        _entry("A", "S9(4)"),
        _entry("INNER", usage="DISPLAY", children=[_entry("B", "S9(2)")]),
        _entry("MID", children=[_entry("C", "9(3)", usage="COMP-3")]),
        _entry("D", "S9(9)"),
    ],
)


def _usages(item: CobolField) -> list[tuple[str, str, int, bool]]:
    return [
        (d.name, d.usage, byte_length(d), d.sign_separate)
        for d in (item, *[g for c in item.children for g in (c, *c.children)])
    ]


def test_items_take_the_nearest_usage_and_it_survives_a_round_trip() -> None:
    read = CobolField.from_dict(_GROUP)
    expected = [
        ("OUTER", "COMP", 11, True),
        ("A", "COMP", 2, False),
        ("INNER", "DISPLAY", 3, False),
        ("B", "DISPLAY", 3, True),
        ("MID", "COMP", 2, False),
        ("C", "COMP-3", 2, False),
        ("D", "COMP", 4, False),
    ]

    assert _usages(read) == expected
    assert _usages(CobolField.from_dict(read.to_dict())) == expected


def test_an_entry_with_no_usage_anywhere_is_display() -> None:
    assert CobolField.from_dict(_entry("X", "X(3)")).usage == "DISPLAY"
