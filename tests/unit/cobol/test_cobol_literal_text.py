"""A nonnumeric literal's characters: delimiters removed, doubled delimiters undone."""

import pytest

from interpreter.cobol.emit_context import strip_cobol_literal


@pytest.mark.parametrize(
    ("literal", "characters"),
    [
        ('"A""B"', 'A"B'),
        ("'IT''S'", "IT'S"),
        ("\"A''B\"", "A''B"),
        ('""""', '"'),
        ('"ABC"', "ABC"),
        ("1,5", "1,5"),
    ],
)
def test_a_doubled_delimiter_stands_for_one(literal: str, characters: str) -> None:
    assert strip_cobol_literal(literal) == characters
