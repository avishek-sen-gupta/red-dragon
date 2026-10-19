"""End-to-end: an indexed file is read and positioned by any of its record keys, which
becomes the key of reference that READ NEXT follows; duplicates of an alternate key are
read in the order written and reported with status 02."""

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


@covers(CobolFeature.START)
@covers(CobolFeature.READ)
def test_reads_follow_the_key_of_reference(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """IBM Enterprise COBOL LR, START, indexed files: the RECORD KEY or ALTERNATE RECORD
    KEY with which data-name-1 is associated becomes the key of reference for subsequent
    READ statements. File status 02: for a READ, the next record in the key of reference
    has the same key value; for a WRITE or REWRITE, the record created a duplicate of an
    alternate key that allows duplicates."""
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ALTKEYS.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F ASSIGN TO "ixf" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS DYNAMIC RECORD KEY IS F-KEY",
            "        ALTERNATE RECORD KEY IS K OF ALT1",
            "        ALTERNATE RECORD KEY IS F-ALT2 WITH DUPLICATES",
            "        FILE STATUS IS FS.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F.",
            "01 F-REC.",
            "   05 F-KEY PIC X.",
            "   05 ALT1. 10 K PIC X.",
            "   05 F-ALT2 PIC X.",
            "WORKING-STORAGE SECTION.",
            "01 FS PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT F.",
            '    MOVE "AZP" TO F-REC. WRITE F-REC. DISPLAY "W " FS.',
            '    MOVE "BYQ" TO F-REC. WRITE F-REC. DISPLAY "W " FS.',
            '    MOVE "CXP" TO F-REC. WRITE F-REC. DISPLAY "W " FS.',
            '    MOVE "DXS" TO F-REC. WRITE F-REC. DISPLAY "W " FS.',
            "    CLOSE F.",
            "    OPEN I-O F.",
            '    MOVE "Y" TO K OF ALT1.',
            "    READ F KEY IS K OF ALT1.",
            '    DISPLAY "K " FS " " F-REC.',
            "    READ F NEXT. DISPLAY F-REC.",
            "    READ F NEXT. DISPLAY FS.",
            '    MOVE "B" TO F-KEY. READ F. READ F NEXT. DISPLAY F-REC.',
            '    MOVE "P" TO F-ALT2.',
            "    START F KEY IS EQUAL TO F-ALT2.",
            "    READ F NEXT. DISPLAY FS F-REC.",
            "    READ F NEXT. DISPLAY FS F-REC.",
            "    READ F NEXT. DISPLAY FS F-REC.",
            "    CLOSE F.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=20000,
        io_provider=RealFileIOProvider(base_dir=tmp_path),
    )
    assert capsys.readouterr().out == (
        "W 00\nW 00\nW 02\nW 22\n" "K 00 BYQ\nAZP\n10\n" "CXP\n" "02AZP\n00CXP\n00BYQ\n"
    )
