"""A group's SIGN clause applies to each signed numeric DISPLAY item under it."""

from collections.abc import Sequence

from cobol_asg.cobol_field import CobolField


def _entry(name: str, pic: str = "", **clauses: str | bool | dict | list) -> dict:
    return {"name": name, "level": 5, "pic": pic, "usage": "DISPLAY"} | clauses


_GROUP = _entry(
    "OUTER",
    sign={"position": "LEADING", "separate": True},
    children=[
        _entry("A", "S9(2)"),
        _entry(
            "INNER",
            sign={"position": "TRAILING", "separate": False},
            children=[
                _entry("B", "S9(2)"),
                _entry("C", "S9(2)", sign={"separate": True}),
            ],
        ),
        _entry("MID", children=[_entry("F", "S9(2)")]),
        _entry("D", "9(2)"),
        _entry("E", "S9(2)", usage="COMP"),
    ],
)


def _signs(fields: Sequence[CobolField]) -> list[tuple[str, bool, bool]]:
    return [
        (d.name, d.sign_leading, d.sign_separate)
        for f in fields
        for d in (f, *[g for c in f.children for g in (c, *c.children)])
    ]


def test_the_nearest_clause_applies_and_survives_a_round_trip() -> None:
    read = CobolField.from_dict(_GROUP)
    expected = [
        ("OUTER", True, True),
        ("A", True, True),
        ("INNER", False, False),
        ("B", False, False),
        ("C", False, True),
        ("MID", False, False),
        ("F", True, True),
        ("D", False, False),
        ("E", False, False),
    ]

    assert _signs([read]) == expected
    assert _signs([CobolField.from_dict(read.to_dict())]) == expected
