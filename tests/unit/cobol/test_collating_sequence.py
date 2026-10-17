"""A program collating sequence built from an ALPHABET clause."""

from collections.abc import Mapping, Sequence

from cobol_asg.alphabet import NATIVE_ALPHABET, Alphabet
from cobol_asg.asg_types import CobolASG
from interpreter.cobol.collating_sequences import collating_sequence_of
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


def _byte(character: str) -> int:
    return EbcdicTable.ASCII_TO_EBCDIC[ord(character)]


def _items(*items: tuple[str, str, str]) -> list[dict[str, str]]:
    return [{"link": link, "kind": kind, "value": value} for link, kind, value in items]


def _special_names(name: str, items: Sequence[Mapping[str, str]]) -> dict:
    return {
        "special_names": {
            "program_collating_sequence": {
                "name": name,
                "kind": "LITERALS",
                "items": items,
            },
        }
    }


@covers(CobolFeature.PROGRAM_COLLATING_SEQUENCE)
def test_literal_phrase_orders_named_characters_first_and_the_rest_natively():
    asg = CobolASG.from_dict(
        _special_names(
            "SEQ",
            _items(
                ("NONE", "NONNUMERIC", "FU"),
                ("NONE", "NONNUMERIC", "N"),
                ("ALSO", "FIGURATIVE", "HIGH-VALUE"),
                ("ALSO", "FIGURATIVE", "LOW-VALUE"),
                ("NONE", "NONNUMERIC", "C"),
                ("THRU", "NONNUMERIC", "A"),
                ("NONE", "NUMERIC", "2"),
            ),
        )
    )
    sequence = collating_sequence_of(asg.collating_sequence)
    rest = [
        b for b in range(256) if b not in {0x00, 0x01, 0xFF} | set(map(_byte, "FUNCBA"))
    ]

    assert [sequence.weights[_byte(c)] for c in "FUNCBA"] == [0, 1, 2, 3, 4, 5]
    assert [sequence.weights[b] for b in (0xFF, 0x00, 0x01)] == [2, 2, 6]
    assert [sequence.weights[b] for b in rest] == list(range(7, 7 + len(rest)))
    assert (sequence.low_value, sequence.high_value) == (_byte("F"), rest[-1])
    assert (
        CobolASG.from_dict(asg.to_dict()).collating_sequence == asg.collating_sequence
    )


@covers(CobolFeature.PROGRAM_COLLATING_SEQUENCE)
def test_figuratives_and_comparison_order_follow_the_sequence():
    alphabet = Alphabet.from_parts(
        "SEQ",
        "LITERALS",
        _items(("NONE", "NONNUMERIC", "Q"), ("ALSO", "NONNUMERIC", "R")),
    )
    sequence = collating_sequence_of(alphabet)
    figuratives = sequence.figuratives()
    native, ordinals = sequence.ordinal_alphabets()
    ordering = str.maketrans(native, ordinals)

    assert (figuratives.translate("LOW-VALUES"), figuratives.raw_byte("low-value")) == (
        "Q",
        _byte("Q"),
    )
    assert (
        figuratives.translate("HIGH-VALUE"),
        figuratives.raw_byte("HIGH-VALUES"),
    ) == (
        chr(EbcdicTable.EBCDIC_TO_ASCII[0xFF]),
        0xFF,
    )
    assert (figuratives.translate("SPACES"), figuratives.is_raw("SPACES")) == (
        " ",
        False,
    )
    assert [
        "QR".translate(ordering) == "RQ".translate(ordering),
        "R ".translate(ordering) < " Q".translate(ordering),
    ] == [True, True]


@covers(CobolFeature.PROGRAM_COLLATING_SEQUENCE)
def test_named_character_sets_and_an_absent_clause():
    native = collating_sequence_of(NATIVE_ALPHABET)
    ascii_ = collating_sequence_of(Alphabet.from_parts("A", "STANDARD-1", []))

    assert CobolASG.from_dict({}).collating_sequence == NATIVE_ALPHABET
    assert (
        native.weights[_byte("a")]
        < native.weights[_byte("A")]
        < native.weights[_byte("1")]
    ) is True
    assert (native.low_value, native.high_value) == (0x00, 0xFF)
    assert (
        ascii_.weights[_byte("1")]
        < ascii_.weights[_byte("A")]
        < ascii_.weights[_byte("a")]
    ) is True
    assert [ascii_.weights[_byte(c)] for c in " A"] == [0x20, 0x41]
    assert (ascii_.low_value, ascii_.high_value) == (
        0x00,
        EbcdicTable.ASCII_TO_EBCDIC[0xFF],
    )
