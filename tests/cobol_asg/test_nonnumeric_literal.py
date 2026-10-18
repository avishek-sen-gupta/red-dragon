"""A nonnumeric literal's characters: delimiters removed, doubled delimiters undone."""

import pytest

from cobol_asg.nonnumeric_literal import literal_characters, written_literal


@pytest.mark.parametrize(
    ("literal", "characters"),
    [
        ('"A""B"', 'A"B'),
        ("'IT''S'", "IT'S"),
        ("\"A''B\"", "A''B"),
        ('""""', '"'),
        ('"ABC"', "ABC"),
        ("\"'X'\"", "'X'"),
        ("1,5", "1,5"),
    ],
)
def test_a_doubled_delimiter_stands_for_one(literal: str, characters: str) -> None:
    assert literal_characters(literal) == characters
    assert literal_characters(written_literal(characters)) == characters


def test_the_asg_reader_decodes_each_literal_once_and_writes_it_back() -> None:
    from cobol_asg.alphabet_item import AlphabetItem
    from cobol_asg.cobol_field import CobolField
    from cobol_asg.condition_name import ConditionValue

    field = CobolField.from_dict(
        {
            "name": "W",
            "level": 1,
            "pic": "X(3)",
            "value": "\"'X'\"",
            "conditions": [
                {
                    "name": "C",
                    "values": [
                        {"from": "'''Y'''", "to": ""},
                        {"from": "SPACES", "to": "", "figurative": True},
                        {"from": "1", "to": "3", "numeric": True},
                    ],
                }
            ],
        }
    )
    item = AlphabetItem.from_dict(
        {"link": "NONE", "kind": "NONNUMERIC", "value": "'A''B'"}
    )

    assert (field.value, field.conditions[0].values, item.value) == (
        "'X'",
        [
            ConditionValue(from_val="'Y'"),
            ConditionValue(from_val="SPACES", figurative=True),
            ConditionValue(from_val="1", to_val="3", numeric=True),
        ],
        "A'B",
    )
    assert CobolField.from_dict(field.to_dict()) == field
    assert AlphabetItem.from_dict(item.to_dict()) == item
