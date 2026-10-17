"""Tests for the INSPECT engine: one left-to-right scan with every phrase competing."""

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.inspect_mode import InspectMode
from interpreter.cobol.inspect_phrase import InspectPhrase
from interpreter.cobol.inspect_scan import (
    inspect_convert,
    inspect_replace,
    inspect_tally,
)
from tests.covers import covers

_ALL = InspectMode.ALL
_LEADING = InspectMode.LEADING
_FIRST = InspectMode.FIRST
_CHARS = InspectMode.CHARACTERS

_WC = "AH YES AH YES W.C. FRITOES HERE. ANYONE WHO HATES DOGS AND KIDS CAN NOT BE ALL BAD."


@covers(CobolFeature.INSPECT_TALLYING)
def test_tallying_counts_each_position_once_within_each_phrase_region():
    cases = [
        (_WC, (InspectPhrase(_CHARS),), 1),
        (_WC, (InspectPhrase(_CHARS, after=" W"),), 1),
        (_WC, (InspectPhrase(_CHARS, after=" W", before="KI"),), 1),
        (_WC, (InspectPhrase(_ALL, " ", after="C.", before="DO"),), 1),
        ("ABCXYZ", (InspectPhrase(_ALL, "B", after="Q"),), 1),
        ("ABCXYZ", (InspectPhrase(_ALL, "B", before="Q"),), 1),
        ("AABA", (InspectPhrase(_ALL, "AA"), InspectPhrase(_ALL, "A", counter=1)), 2),
        ("AAXAA", (InspectPhrase(_LEADING, "A"),), 1),
        ("XAAXA", (InspectPhrase(_LEADING, "A", after="X"),), 1),
        (
            "ABAB",
            (InspectPhrase(_ALL, "A"), InspectPhrase(_CHARS, counter=1)),
            2,
        ),
        ("AB", (InspectPhrase(_ALL, ""),), 1),
    ]
    assert [inspect_tally(source, phrases, n) for source, phrases, n in cases] == [
        (83,),
        (68,),
        (44,),
        (6,),
        (0,),
        (1,),
        (1, 1),
        (2,),
        (2,),
        (2, 2),
        (0,),
    ]


@covers(CobolFeature.INSPECT_REPLACING)
def test_replacing_rewrites_matched_positions_in_one_scan():
    cases = [
        ("AB", (InspectPhrase(_ALL, "A", "B"), InspectPhrase(_ALL, "B", "C"))),
        ("AABAC", (InspectPhrase(_FIRST, "A", "X"),)),
        ("AACAA", (InspectPhrase(_LEADING, "A", "Z"),)),
        ("HELLO", (InspectPhrase(_CHARS, "", "O", before="L"),)),
        ("HELLO", (InspectPhrase(_CHARS, "", " "),)),
        ("ABCXYZ", (InspectPhrase(_ALL, "B", "-", after="Q"),)),
        (
            "AAEECEE",
            (InspectPhrase(_FIRST, "C", "2"), InspectPhrase(_ALL, "E", "3", after="C")),
        ),
        ("A.B.", (InspectPhrase(_ALL, ".", " "),)),
        ("ABAB", (InspectPhrase(_ALL, "AB", " "),)),
    ]
    assert [inspect_replace(source, phrases) for source, phrases in cases] == [
        "BC",
        "XABAC",
        "ZZCAA",
        "OOLLO",
        "     ",
        "ABCXYZ",
        "AAEE233",
        "A B ",
        "    ",
    ]


@covers(CobolFeature.INSPECT_CONVERTING)
def test_converting_translates_only_inside_its_region():
    assert [
        inspect_convert("GAQAUZTABAGA", "AU", "23", "Q", "B"),
        inspect_convert("GAQAUZTABAGA", "AU", "23", "", ""),
        inspect_convert("ABCABC", "AA", "XY", "", ""),
        inspect_convert("ABC", "A", "X", "Q", ""),
    ] == ["GAQ23ZT2BAGA", "G2Q23ZT2B2G2", "XBCXBC", "ABC"]
