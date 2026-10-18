"""The NIST harness maps every SELECT, OPTIONAL ones included, to its X-card file."""

from __future__ import annotations

from tests.covers import NotLanguageFeature, covers
from tests.nist.conftest import extract_file_controls


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_optional_select_is_named_by_its_file_not_the_keyword() -> None:
    source = "\n".join(
        [
            "       FILE-CONTROL.",
            "           SELECT PRINT-FILE ASSIGN TO",
            "           XXXXX055.",
            "           SELECT  OPTIONAL RL-FS1 ASSIGN TO",
            "           XXXXX021",
            "                  ORGANIZATION IS RELATIVE.",
        ]
    )
    assert extract_file_controls(source) == [
        ("PRINT-FILE", "XXXXX055"),
        ("RL-FS1", "XXXXX021"),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_select_past_column_72_of_expanded_text_is_read_whole() -> None:
    line = "           SELECT REPLACED-FILE-WITH-A-LONG-NAME ORGANIZATION IS SEQUENTIAL"
    expanded = f"{line} ASSIGN TO XXXXX021."
    assert len(line) > 72
    assert extract_file_controls(expanded) == [
        ("REPLACED-FILE-WITH-A-LONG-NAME", "XXXXX021")
    ]
