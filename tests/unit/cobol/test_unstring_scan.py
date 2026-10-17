"""Tests for UNSTRING's examination of the source into receiver pieces."""

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.unstring_delimiter_text import UnstringDelimiterText
from interpreter.cobol.unstring_outcome import UnstringOutcome
from interpreter.cobol.unstring_piece import UnstringPiece
from interpreter.cobol.unstring_scan import unstring
from tests.covers import covers

_ZERO = UnstringDelimiterText(text="0", all=False)
_ALL_ZERO = UnstringDelimiterText(text="0", all=True)
_COMMA = UnstringDelimiterText(text=",", all=False)
_COMMA_SPACE = UnstringDelimiterText(text=", ", all=False)


def _piece(text: str, delimiter: str = "") -> UnstringPiece:
    return UnstringPiece(text=text, delimiter=delimiter, count=len(text))


@covers(CobolFeature.UNSTRING_VERB, CobolFeature.UNSTRING_DELIMITED_BY)
def test_each_receiver_takes_the_characters_before_the_nearest_delimiter():
    cases = [
        ("1200300", 1, (_ZERO,), (3, 3, 3)),
        ("1200300", 1, (_ALL_ZERO,), (3, 3, 3)),
        ("000", 1, (_ALL_ZERO,), (2, 2)),
        ("A,B, C", 1, (_COMMA, _COMMA_SPACE), (2, 2, 2)),
        ("A,B, C", 1, (_COMMA_SPACE, _COMMA), (2, 2, 2)),
        ("A,B,C,D", 3, (_COMMA,), (2, 2)),
        ("ABCDEF", 1, (), (2, 3)),
        ("ABCDEF", 2, (), (3, 2)),
        ("ABC", 0, (_COMMA,), (2,)),
        ("ABC", 4, (_COMMA,), (2,)),
    ]
    assert [unstring(*case) for case in cases] == [
        UnstringOutcome(
            pieces=(_piece("12", "0"), _piece("", "0"), _piece("3", "0")),
            pointer=7,
            overflow=True,
        ),
        UnstringOutcome(
            pieces=(_piece("12", "0"), _piece("3", "0")), pointer=8, overflow=False
        ),
        UnstringOutcome(pieces=(_piece("", "0"),), pointer=4, overflow=False),
        UnstringOutcome(
            pieces=(_piece("A", ","), _piece("B", ","), _piece(" C")),
            pointer=7,
            overflow=False,
        ),
        UnstringOutcome(
            pieces=(_piece("A", ","), _piece("B", ", "), _piece("C")),
            pointer=7,
            overflow=False,
        ),
        UnstringOutcome(
            pieces=(_piece("B", ","), _piece("C", ",")), pointer=7, overflow=True
        ),
        UnstringOutcome(pieces=(_piece("AB"), _piece("CDE")), pointer=6, overflow=True),
        UnstringOutcome(
            pieces=(_piece("BCD"), _piece("EF")), pointer=7, overflow=False
        ),
        UnstringOutcome(pieces=(), pointer=0, overflow=True),
        UnstringOutcome(pieces=(), pointer=4, overflow=True),
    ]
