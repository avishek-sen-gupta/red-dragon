"""Tests for STRING's transfer of the delimited sendings into the receiver."""

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.string_outcome import StringOutcome
from interpreter.cobol.string_transfer import string_into
from tests.covers import covers


@covers(CobolFeature.STRING_VERB)
def test_transfer_stops_at_the_receiver_end_and_moves_the_pointer_by_what_fitted():
    cases = [
        ("*****", 1, ("ABCDEF",)),
        ("*****", 1, ("AB", "CDE")),
        ("*****", 2, ("AB",)),
        ("*****", 3, ("ABCD", "EFGH", "IJKL")),
        ("*****", 0, ("A",)),
        ("*****", 6, ("A",)),
        ("*****", 6, ()),
        ("*****", 1, ("", "")),
    ]
    assert [string_into(*case) for case in cases] == [
        StringOutcome(image="ABCDE", pointer=6, overflow=True),
        StringOutcome(image="ABCDE", pointer=6, overflow=False),
        StringOutcome(image="*AB**", pointer=4, overflow=False),
        StringOutcome(image="**ABC", pointer=6, overflow=True),
        StringOutcome(image="*****", pointer=0, overflow=True),
        StringOutcome(image="*****", pointer=6, overflow=True),
        StringOutcome(image="*****", pointer=6, overflow=True),
        StringOutcome(image="*****", pointer=1, overflow=False),
    ]
