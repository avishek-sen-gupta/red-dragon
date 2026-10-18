"""End-to-end: OPEN passes a file's ACCESS MODE and RELATIVE KEY size, so sequential
access yields the I-O statuses 21, 43 and 14."""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.cobol.run_inputs import RunInputs
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    to_fixed,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


@covers(CobolFeature.OPEN)
@covers(CobolFeature.WRITE)
@covers(CobolFeature.REWRITE)
@covers(CobolFeature.READ)
def test_sequential_access_statuses_follow_the_select_entry(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ACCSTAT.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT IX ASSIGN TO "ixf" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS SEQUENTIAL RECORD KEY IS IX-KEY",
            "        FILE STATUS IS ST.",
            '    SELECT RL ASSIGN TO "rlf" ORGANIZATION IS RELATIVE',
            "        ACCESS MODE IS SEQUENTIAL RELATIVE KEY IS RK",
            "        FILE STATUS IS ST.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD IX.",
            "01 IX-REC.",
            "   05 IX-TAG PIC X.",
            "   05 IX-KEY PIC 99.",
            "FD RL.",
            "01 RL-REC PIC X.",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "01 RK PIC 9.",
            "01 N PIC 99 VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IX.",
            '    MOVE "A20" TO IX-REC. WRITE IX-REC. DISPLAY ST.',
            '    MOVE "B10" TO IX-REC. WRITE IX-REC',
            '        INVALID KEY DISPLAY "I " ST END-WRITE.',
            "    CLOSE IX.",
            "    OPEN I-O IX.",
            "    REWRITE IX-REC. DISPLAY ST.",
            "    READ IX. MOVE 30 TO IX-KEY.",
            '    REWRITE IX-REC INVALID KEY DISPLAY "I " ST END-REWRITE.',
            "    CLOSE IX.",
            "    OPEN OUTPUT RL.",
            "    PERFORM 10 TIMES WRITE RL-REC END-PERFORM.",
            "    CLOSE RL.",
            "    OPEN INPUT RL.",
            '    PERFORM UNTIL ST NOT = SPACES AND ST NOT = "00"',
            '        READ RL AT END DISPLAY "E " ST " " N " " RK',
            "            NOT AT END ADD 1 TO N END-READ",
            "    END-PERFORM.",
            "    CLOSE RL.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=50000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(
                path_overrides={"IX": tmp_path / "ixf", "RL": tmp_path / "rlf"}
            ),
        ),
    )
    assert capsys.readouterr().out == "00\nI 21\n43\nI 21\nE 14 09 9\n"
