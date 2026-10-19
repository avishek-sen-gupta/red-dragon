"""The NIST harness supplies X-card values and the ACCEPT input deck."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.ebcdic_table import EbcdicTable
from tests.nist.conftest import input_deck, substitute_x_cards


def test_x_cards_are_substituted_within_the_program_text_area() -> None:
    source = "\n".join(
        [
            "181400     MOVE".ljust(72) + "NC1034.2",
            "181500     XXXXX081".ljust(72) + "NC1034.2",
            "181600     TO NON-COBOL-CHARACTERS.".ljust(72) + "NC1034.2",
            "002800     XXXXX082.".ljust(72) + "NC1034.2",
            "044800     XXXXX065".ljust(72) + "ST1154.2",
            '174400     MOVE "GGGGHXXXXX052ALTKEY1" TO K.'.ljust(72) + "IX2094.2",
            '174500     MOVE "XXXXX081ALTKEY2" TO K.'.ljust(72) + "IX2094.2",
        ]
    )
    assert substitute_x_cards(source).splitlines() == [
        "181400     MOVE".ljust(72) + "NC1034.2",
        '181500     "12345678"'.ljust(72) + "NC1034.2",
        "181600     TO NON-COBOL-CHARACTERS.".ljust(72) + "NC1034.2",
        "002800     XXXXX082.".ljust(72) + "NC1034.2",
        "044800     0200".ljust(72) + "ST1154.2",
        '174400     MOVE "GGGGHXXXXX052ALTKEY1" TO K.'.ljust(72) + "IX2094.2",
        '174500     MOVE "XXXXX081ALTKEY2" TO K.'.ljust(72) + "IX2094.2",
    ]


def test_input_deck_is_the_data_cards_as_80_column_records(tmp_path: Path) -> None:
    deck = tmp_path / "NC999M.DAT"
    deck.write_text(
        "      *HEADER,DATA*,NC999M".ljust(86)
        + "\n"
        + "ABC\n"
        + "D".ljust(85, "*")
        + "\n"
        + "      *END-OF,NC999M".ljust(86)
        + "\n"
    )
    assert (input_deck(deck), input_deck(tmp_path / "NC998M.DAT")) == (
        ["ABC".ljust(80), "D".ljust(80, "*")],
        [],
    )


_CCVS_COLLATING_CHARACTERS = " $$()*+,-./0123456789;<=>ABCDEFGHIJKLMNOPQRSTUVWXYZ"


_LITERAL_START = 12


def _card(name: str) -> str:
    line = substitute_x_cards(f"000100     {name}.".ljust(72) + "ST1374.2")
    return line[_LITERAL_START : line.index('".') + 1].strip('"')


def test_x_cards_63_and_64_are_the_ccvs_characters_in_native_order() -> None:
    ascending, descending = _card("XXXXX063"), _card("XXXXX064")
    assert (
        sorted(ascending),
        "".join(sorted(ascending, key=lambda c: EbcdicTable.ASCII_TO_EBCDIC[ord(c)])),
        descending,
    ) == (sorted(_CCVS_COLLATING_CHARACTERS), ascending, ascending[::-1])
