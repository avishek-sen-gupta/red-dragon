"""End-to-end: a relative file's verbs use and update its RELATIVE KEY."""

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


@covers(CobolFeature.WRITE)
@covers(CobolFeature.READ)
@covers(CobolFeature.REWRITE)
@covers(CobolFeature.DELETE_RECORD)
def test_relative_key_addresses_and_reports_record_numbers(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. RELKEY.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT S ASSIGN TO "rlf" ORGANIZATION IS RELATIVE',
            "        ACCESS MODE IS SEQUENTIAL RELATIVE KEY IS SK",
            "        FILE STATUS IS ST.",
            '    SELECT F ASSIGN TO "rlf" ORGANIZATION IS RELATIVE',
            "        ACCESS MODE IS DYNAMIC RELATIVE KEY IS RK",
            "        FILE STATUS IS ST.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD S.",
            "01 S-REC PIC X(3).",
            "FD F.",
            "01 F-REC PIC X(3).",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "01 SK PIC 9(4).",
            "01 RK PIC 9(4).",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT S.",
            '    MOVE "ONE" TO S-REC. WRITE S-REC. DISPLAY SK.',
            '    MOVE "TWO" TO S-REC. WRITE S-REC. DISPLAY SK.',
            "    CLOSE S.",
            "    OPEN I-O F.",
            '    MOVE 2 TO RK. MOVE "DUP" TO F-REC.',
            '    WRITE F-REC. DISPLAY "W " ST.',
            '    MOVE 5 TO RK. MOVE "FIV" TO F-REC. WRITE F-REC.',
            '    MOVE 4 TO RK. READ F. DISPLAY "R " ST.',
            '    MOVE 2 TO RK. READ F. DISPLAY F-REC " " RK.',
            '    MOVE "NEW" TO F-REC. MOVE 1 TO RK. REWRITE F-REC.',
            "    MOVE 2 TO RK. DELETE F RECORD.",
            "    MOVE 1 TO RK. READ F. DISPLAY F-REC.",
            "    CLOSE F.",
            "    OPEN INPUT S. READ S. READ S. DISPLAY S-REC SK. CLOSE S.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=20000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            path_overrides={"S": tmp_path / "rlf", "F": tmp_path / "rlf"},
        ),
    )
    assert capsys.readouterr().out == (
        "0001\n0002\nW 22\nR 23\nTWO 0002\nNEW\nFIV0005\n"
    )
