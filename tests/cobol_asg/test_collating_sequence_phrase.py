"""A COLLATING SEQUENCE phrase names its alphabet; the ASG reader resolves the name."""

import pytest

from cobol_asg.alphabet import Alphabet
from cobol_asg.collating_sequence_phrase import CollatingSequencePhrase

_ALPHABETS = (
    Alphabet.from_parts("FIRST", "STANDARD-1", []),
    Alphabet.from_parts("OTHER", "EBCDIC", []),
)


def test_for_alphanumeric_wins_and_otherwise_the_first_name() -> None:
    written = CollatingSequencePhrase.from_dict({"alphabet_names": ["FIRST", "OTHER"]})
    paired = CollatingSequencePhrase.from_dict(
        {"alphabet_names": [], "alphanumeric": "OTHER", "national": "N"}
    )

    assert written.alphanumeric_alphabet(_ALPHABETS) == _ALPHABETS[0]
    assert paired.alphanumeric_alphabet(_ALPHABETS) == _ALPHABETS[1]
    assert CollatingSequencePhrase.from_dict(paired.to_dict()) == paired


def test_an_undeclared_alphabet_is_refused() -> None:
    with pytest.raises(ValueError, match="names alphabet MISSING"):
        CollatingSequencePhrase(alphabet_names=("MISSING",)).alphanumeric_alphabet(
            _ALPHABETS
        )
