"""End-to-end: an FD's LINAGE clause gives its file a logical page, a LINAGE-COUNTER the
program reads, and the end-of-page condition WRITE's END-OF-PAGE phrases respond to."""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    to_fixed,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


def _run(lines: list[str], tmp_path: Path) -> None:
    run(
        source=to_fixed(lines),
        language="cobol",
        max_steps=20000,
        io_provider=RealFileIOProvider(base_dir=tmp_path),
    )


@covers(CobolFeature.WRITE)
def test_linage_counter_follows_open_advancing_and_page_overflow(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """IBM Enterprise COBOL LR, LINAGE-COUNTER: it is initialized to 1 when an OPEN
    statement for its file is executed. WRITE, LINAGE-COUNTER rules: ADVANCING PAGE
    resets it to 1; ADVANCING n adds n; without ADVANCING it is increased by 1; when
    the device is repositioned to the first line of a new page it is reset to 1, which
    a WRITE that would exceed the page body does. Advancing writes no lines of its own:
    the file holds one record per WRITE."""
    _run(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. LINCTR.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT P ASSIGN TO "pf".',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD P LINAGE IS 5 LINES WITH FOOTING AT 4",
            "    LINES AT TOP 1 LINES AT BOTTOM 1.",
            "01 P-REC PIC X(4).",
            "WORKING-STORAGE SECTION.",
            "77 N PIC 9 VALUE 1.",
            "77 K PIC 9 VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT P. DISPLAY LINAGE-COUNTER.",
            '    MOVE "AAAA" TO P-REC.',
            "    WRITE P-REC. DISPLAY LINAGE-COUNTER.",
            "    WRITE P-REC AFTER ADVANCING 2 LINES. DISPLAY LINAGE-COUNTER.",
            "    WRITE P-REC BEFORE ADVANCING N LINE. DISPLAY LINAGE-COUNTER.",
            "    WRITE P-REC AFTER ADVANCING 1 LINE. DISPLAY LINAGE-COUNTER.",
            "    WRITE P-REC AFTER 3. DISPLAY LINAGE-COUNTER.",
            "    WRITE P-REC BEFORE ADVANCING PAGE. DISPLAY LINAGE-COUNTER.",
            "    WRITE P-REC AFTER 2. WRITE P-REC AFTER PAGE.",
            "    DISPLAY LINAGE-COUNTER.",
            "    CLOSE P. OPEN INPUT P.",
            "    PERFORM UNTIL K = 9",
            "        READ P AT END DISPLAY K MOVE 9 TO K",
            "        NOT AT END ADD 1 TO K END-READ",
            "    END-PERFORM.",
            "    CLOSE P.",
            "    STOP RUN.",
        ],
        tmp_path,
    )
    assert capsys.readouterr().out == "1\n2\n4\n5\n1\n4\n1\n1\n8\n"


@covers(CobolFeature.WRITE)
def test_end_of_page_phrases_follow_footing_area_and_page_overflow(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """IBM Enterprise COBOL LR, WRITE, END-OF-PAGE phrases: the end-of-page condition is
    reached when a WRITE causes LINAGE-COUNTER to equal or exceed the footing value, and
    automatic page overflow when it would exceed the page body; on either the END-OF-PAGE
    imperative statement runs after the WRITE. Without WITH FOOTING only page overflow
    reaches the end of the page. A LINAGE-COUNTER is qualified by its file's name when
    more than one file has a LINAGE clause."""
    _run(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. LINEOP.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT P ASSIGN TO "pf".',
            '    SELECT Q ASSIGN TO "qf".',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD P LINAGE IS 5 LINES WITH FOOTING AT 3.",
            "01 P-REC PIC X(4).",
            "FD Q LINAGE IS 3 LINES.",
            "01 Q-REC PIC X(4).",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT P Q.",
            "    PERFORM 6 TIMES",
            "        WRITE P-REC BEFORE ADVANCING 1 LINE",
            '            AT END-OF-PAGE DISPLAY "E" LINAGE-COUNTER OF P',
            '            NOT AT END-OF-PAGE DISPLAY "N" LINAGE-COUNTER OF P',
            "        END-WRITE",
            "    END-PERFORM.",
            "    PERFORM 3 TIMES",
            "        WRITE Q-REC AT EOP DISPLAY " '"E" LINAGE-COUNTER IN Q',
            '            NOT AT EOP DISPLAY "N" LINAGE-COUNTER IN Q',
            "        END-WRITE",
            "    END-PERFORM.",
            "    CLOSE P Q.",
            "    STOP RUN.",
        ],
        tmp_path,
    )
    assert capsys.readouterr().out == "N2\nE3\nE4\nE5\nE1\nN2\nN2\nN3\nE1\n"


@covers(CobolFeature.WRITE)
def test_linage_data_names_set_each_page_when_it_begins(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """IBM Enterprise COBOL LR, LINAGE clause: OPEN takes the page body and footing from
    the data-names for the first logical page only; a WRITE ADVANCING PAGE or a page
    overflow takes them for the next page. LINAGE-COUNTER: for a data-name it has that
    data-name's PICTURE and USAGE."""
    _run(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. LINDN.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT P ASSIGN TO "pf".',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD P LINAGE IS L LINES FOOTING F.",
            "01 P-REC PIC X(4).",
            "WORKING-STORAGE SECTION.",
            "77 L PIC 99 VALUE 3.",
            "77 F PIC 99 VALUE 3.",
            "77 K PIC 99 VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT P.",
            "    MOVE 9 TO L. MOVE 8 TO F.",
            "    PERFORM 4 TIMES",
            '        WRITE P-REC AT EOP DISPLAY "E" LINAGE-COUNTER',
            '            NOT AT EOP DISPLAY "N" LINAGE-COUNTER END-WRITE',
            "    END-PERFORM.",
            "    PERFORM UNTIL LINAGE-COUNTER = 9",
            "        WRITE P-REC ADD 1 TO K",
            "    END-PERFORM.",
            "    DISPLAY K.",
            "    CLOSE P.",
            "    STOP RUN.",
        ],
        tmp_path,
    )
    assert capsys.readouterr().out == "N02\nE03\nE01\nN02\n07\n"
