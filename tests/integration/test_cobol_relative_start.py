"""End-to-end: START of a relative file positions at the first record whose number
satisfies the relation with the RELATIVE KEY, or takes INVALID KEY when none does."""

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
def test_relative_start_honours_its_relation(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. RLSTART.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT R ASSIGN TO "rls" ORGANIZATION IS RELATIVE',
            "        ACCESS MODE IS DYNAMIC RELATIVE KEY IS RK",
            "        FILE STATUS IS ST.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD R.",
            "01 R-REC PIC X.",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "01 RK PIC 9.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT R.",
            '    MOVE 2 TO RK. MOVE "B" TO R-REC. WRITE R-REC.',
            '    MOVE 5 TO RK. MOVE "E" TO R-REC. WRITE R-REC.',
            "    CLOSE R.",
            "    OPEN INPUT R.",
            "    MOVE 2 TO RK. START R KEY IS GREATER THAN RK.",
            "    READ R NEXT. DISPLAY ST R-REC RK.",
            "    MOVE 3 TO RK. START R KEY IS EQUAL TO RK",
            '        INVALID KEY DISPLAY "I " ST END-START.',
            "    MOVE 1 TO RK. START R KEY IS NOT LESS THAN RK.",
            "    READ R NEXT. DISPLAY ST R-REC RK.",
            "    MOVE 5 TO RK. START R KEY IS GREATER THAN RK",
            '        INVALID KEY DISPLAY "I " ST END-START.',
            "    CLOSE R.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=20000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path, inputs=RunInputs(path_overrides={"R": tmp_path / "rls"})
        ),
    )
    assert capsys.readouterr().out == "00E5\nI 23\n00B2\nI 23\n"
