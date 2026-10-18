"""End-to-end: SELECT OPTIONAL lets an absent file open with status 05, empty for
INPUT and created for EXTEND."""

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
@covers(CobolFeature.READ)
def test_an_absent_optional_file_opens_with_status_05(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. OPTF.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT OPTIONAL F ASSIGN TO "optf" FILE STATUS IS ST.',
            '    SELECT G ASSIGN TO "nopt" FILE STATUS IS ST.',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F.",
            "01 F-REC PIC X(2).",
            "FD G.",
            "01 G-REC PIC X(2).",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN INPUT F. DISPLAY ST.",
            '    READ F AT END DISPLAY "E " ST END-READ.',
            "    CLOSE F.",
            "    OPEN EXTEND F. DISPLAY ST.",
            '    MOVE "AB" TO F-REC. WRITE F-REC. CLOSE F.',
            "    OPEN INPUT F. DISPLAY ST. READ F. DISPLAY F-REC. CLOSE F.",
            "    OPEN INPUT G. DISPLAY ST.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=20000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(
                path_overrides={"F": tmp_path / "optf", "G": tmp_path / "nopt"}
            ),
        ),
    )
    assert capsys.readouterr().out == "05\nE 10\n05\n00\nAB\n35\n"
