"""The NIST harness maps the file controls of the text the compiler sees, copied text included."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.cobol_parser import make_cobol_parser
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import to_fixed
from tests.nist.conftest import expanded_file_controls


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_select_copied_with_replacing_is_mapped_by_its_replaced_name(
    tmp_path: Path,
) -> None:
    (tmp_path / "FCBOOK.CPY").write_text(
        to_fixed(["    SELECT DUMMY-FILE ASSIGN TO", "    XXXXP002."])
    )
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. FCTEST.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            "    SELECT PRINT-FILE ASSIGN TO",
            "    XXXXX055.",
            "    COPY FCBOOK REPLACING DUMMY-FILE BY TEST-FILE.",
            "DATA DIVISION.",
            "PROCEDURE DIVISION.",
            "    STOP RUN.",
        ]
    )
    parser = make_cobol_parser(copybook_dirs=[tmp_path])

    assert expanded_file_controls(parser, [source]) == [
        ("PRINT-FILE", "XXXXX055"),
        ("TEST-FILE", "XXXXP002"),
    ]
