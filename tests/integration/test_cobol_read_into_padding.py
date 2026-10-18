"""End-to-end: READ ... INTO moves the record to the INTO item as an alphanumeric move,
so a longer item is filled out with spaces and a shorter one is truncated; an
unsuccessful READ leaves the item alone."""

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


@covers(CobolFeature.READ)
def test_read_into_space_fills_a_longer_item(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. RDINTO.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F ASSIGN TO "rdi".',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F.",
            "01 F-REC PIC X(3).",
            "WORKING-STORAGE SECTION.",
            '01 LONGER PIC X(5) VALUE "ZZZZZ".',
            '01 SHORTER PIC X(2) VALUE "ZZ".',
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT F.",
            '    MOVE "ABC" TO F-REC. WRITE F-REC. WRITE F-REC.',
            "    CLOSE F.",
            "    OPEN INPUT F.",
            '    READ F INTO LONGER. DISPLAY "[" LONGER "]".',
            '    READ F INTO SHORTER. DISPLAY "[" SHORTER "]".',
            '    READ F INTO LONGER AT END DISPLAY "E [" LONGER "]" END-READ.',
            "    CLOSE F.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=20000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path, inputs=RunInputs(path_overrides={"F": tmp_path / "rdi"})
        ),
    )
    assert capsys.readouterr().out == "[ABC  ]\n[AB]\nE [ABC  ]\n"
