"""End-to-end: misused file verbs set the ANSI X3.23-1985 logic-error I-O statuses."""

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


@covers(CobolFeature.OPEN)
@covers(CobolFeature.CLOSE)
@covers(CobolFeature.READ)
@covers(CobolFeature.WRITE)
@covers(CobolFeature.REWRITE)
def test_misused_sequential_file_verbs_report_logic_errors(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. FSTAT.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F ASSIGN TO "sqf" FILE STATUS IS ST.',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F.",
            "01 F-REC PIC X(4).",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            '    MOVE "AAAA" TO F-REC.',
            "    WRITE F-REC. DISPLAY ST.",
            "    OPEN OUTPUT F. WRITE F-REC. READ F. DISPLAY ST.",
            "    CLOSE F.",
            "    OPEN INPUT F. OPEN INPUT F. DISPLAY ST.",
            "    READ F. READ F. READ F. DISPLAY ST.",
            "    CLOSE F. CLOSE F. DISPLAY ST.",
            "    OPEN I-O F. REWRITE F-REC. DISPLAY ST.",
            "    WRITE F-REC. DISPLAY ST.",
            "    CLOSE F.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=5000,
        io_provider=RealFileIOProvider(base_dir=tmp_path),
    )
    assert capsys.readouterr().out == "48\n47\n41\n46\n42\n43\n48\n"
