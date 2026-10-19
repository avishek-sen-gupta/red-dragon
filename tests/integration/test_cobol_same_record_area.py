"""End-to-end: the files a SAME RECORD AREA clause names share one record area, so a
record read into one is the record of the others; files outside it keep their own."""

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


@covers(CobolFeature.READ)
def test_files_in_a_same_record_area_share_their_record(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """ANSI X3.23-1985 I-O-CONTROL, SAME RECORD AREA (from memory): the files named
    share the storage area of the current logical record; all records of all those
    files are implicit redefinitions of that area."""
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. SAMEA.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F1 ASSIGN TO "f1" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS DYNAMIC RECORD KEY IS K1.",
            '    SELECT P ASSIGN TO "pf".',
            '    SELECT F2 ASSIGN TO "f2" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS DYNAMIC RECORD KEY IS K2.",
            "I-O-CONTROL.",
            "    SAME RECORD AREA FOR F1 F2.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F1.",
            "01 R1.",
            "   05 K1 PIC X.",
            "   05 D1 PIC XXX.",
            "FD P.",
            "01 P-REC PIC X(4).",
            "FD F2.",
            "01 R2.",
            "   05 K2 PIC X.",
            "   05 D2 PIC XXXXX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT F1 F2.",
            '    MOVE "AONE" TO R1. WRITE R1.',
            '    MOVE "BTWO99" TO R2. WRITE R2.',
            "    CLOSE F1 F2.",
            '    MOVE "PPPP" TO P-REC.',
            "    OPEN INPUT F1 F2.",
            "    READ F1 NEXT. READ F2 NEXT.",
            '    DISPLAY R1 " " R2 " " P-REC.',
            "    READ F1 NEXT AT END CONTINUE END-READ.",
            '    CLOSE F1 F2. MOVE "C" TO K1. DISPLAY K2.',
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=5000,
        io_provider=RealFileIOProvider(base_dir=tmp_path),
    )
    assert capsys.readouterr().out == "BTWO BTWO99 PPPP\nC\n"
