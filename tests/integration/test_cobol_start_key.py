"""End-to-end: START positions on the value of its KEY data item."""

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
def test_start_positions_on_the_key_items_value(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """ANSI X3.23-1985 Indexed and Relative I-O, START: the file is positioned
    on the first record whose key relates as the operator says to the KEY data
    item's value; without the KEY phrase, EQUAL TO the RECORD KEY or RELATIVE
    KEY is implied."""
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. STKEY.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F ASSIGN TO "ixf" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS DYNAMIC RECORD KEY IS F-KEY.",
            '    SELECT R ASSIGN TO "rlf" ORGANIZATION IS RELATIVE',
            "        ACCESS MODE IS DYNAMIC RELATIVE KEY IS RK.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F.",
            "01 F-REC.",
            "   05 F-KEY PIC X.",
            "   05 F-DATA PIC XXX.",
            "FD R.",
            "01 R-REC PIC XXXX.",
            "WORKING-STORAGE SECTION.",
            "01 RK PIC 9(4).",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT F R.",
            '    MOVE "AONE" TO F-REC R-REC. WRITE F-REC. WRITE R-REC.',
            '    MOVE "BTWO" TO F-REC R-REC. WRITE F-REC. WRITE R-REC.',
            '    MOVE "CSIX" TO F-REC R-REC. WRITE F-REC. WRITE R-REC.',
            "    CLOSE F R.",
            "    OPEN INPUT F R.",
            '    MOVE "B" TO F-KEY OF F-REC.',
            "    START F KEY IS NOT LESS THAN F-KEY OF F-REC.",
            "    READ F NEXT. DISPLAY F-REC.",
            '    MOVE "C" TO F-KEY.',
            "    START F. READ F NEXT. DISPLAY F-REC.",
            "    MOVE 2 TO RK.",
            "    START R KEY IS EQUAL TO RK. READ R NEXT. DISPLAY R-REC.",
            "    CLOSE F R.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=5000,
        io_provider=RealFileIOProvider(base_dir=tmp_path),
    )
    assert capsys.readouterr().out == "BTWO\nCSIX\nBTWO\n"
