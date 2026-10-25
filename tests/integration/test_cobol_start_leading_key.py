"""End-to-end: START on a data item that is the leading part of an indexed file's
record key compares only that many leading bytes."""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.record_io.run_inputs import RunInputs
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    to_fixed,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


@covers(CobolFeature.START)
def test_start_on_the_leading_part_of_the_record_key(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. IXSTART.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT IX ASSIGN TO "ixf" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS DYNAMIC RECORD KEY IS IX-KEY",
            "        FILE STATUS IS ST.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD IX.",
            "01 IX-REC.",
            "   05 IX-KEY.",
            "      10 IX-K1 PIC X.",
            "      10 IX-K2 PIC X.",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IX.",
            '    MOVE "A9" TO IX-KEY. WRITE IX-REC.',
            '    MOVE "B1" TO IX-KEY. WRITE IX-REC.',
            '    MOVE "B2" TO IX-KEY. WRITE IX-REC.',
            '    MOVE "C1" TO IX-KEY. WRITE IX-REC.',
            "    CLOSE IX.",
            "    OPEN INPUT IX.",
            '    MOVE "B" TO IX-K1. START IX KEY IS EQUAL TO IX-K1.',
            "    READ IX NEXT. DISPLAY ST IX-KEY.",
            '    MOVE "B" TO IX-K1. START IX KEY IS GREATER THAN IX-K1.',
            "    READ IX NEXT. DISPLAY ST IX-KEY.",
            '    MOVE "D" TO IX-K1. START IX KEY IS EQUAL TO IX-K1',
            '        INVALID KEY DISPLAY "I " ST END-START.',
            "    CLOSE IX.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=20000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path, inputs=RunInputs(path_overrides={"IX": tmp_path / "ixf"})
        ),
    )
    assert capsys.readouterr().out == "00B1\n00C1\nI 23\n"
