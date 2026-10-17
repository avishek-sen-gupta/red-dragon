"""End-to-end: RECORD IS VARYING ... DEPENDING ON writes each record at the length its
data item holds, READ sets that item to the length read, and a WRITE outside the file's
record sizes or a sequential REWRITE of another length is a boundary violation (44)."""

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
def test_records_vary_in_length_by_their_depending_on_item(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. VARREC.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F ASSIGN TO "vsq" FILE STATUS IS ST.',
            '    SELECT R ASSIGN TO "vrl" ORGANIZATION IS RELATIVE',
            "        ACCESS MODE IS SEQUENTIAL RELATIVE KEY IS RK",
            "        FILE STATUS IS ST.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F RECORD IS VARYING IN SIZE FROM 2 TO 5 DEPENDING ON F-LEN.",
            "01 F-REC PIC X(5).",
            "01 F-SHORT PIC X(2).",
            "FD R RECORD IS VARYING IN SIZE FROM 1 TO 4 DEPENDING ON R-LEN.",
            "01 R-REC PIC X(4).",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "01 F-LEN PIC 99.",
            "01 R-LEN PIC 9.",
            "01 RK PIC 9.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT F.",
            '    MOVE "ABCDE" TO F-REC.',
            '    MOVE 1 TO F-LEN. WRITE F-REC. DISPLAY "W " ST.',
            '    MOVE 6 TO F-LEN. WRITE F-REC. DISPLAY "W " ST.',
            "    MOVE 3 TO F-LEN. WRITE F-SHORT.",
            "    MOVE 5 TO F-LEN. WRITE F-REC.",
            "    CLOSE F.",
            "    OPEN I-O F.",
            "    MOVE SPACES TO F-REC. MOVE 0 TO F-LEN.",
            '    READ F. DISPLAY F-LEN " [" F-REC "]".',
            '    MOVE 4 TO F-LEN. REWRITE F-REC. DISPLAY "RW " ST.',
            "    CLOSE F. OPEN I-O F. READ F.",
            '    MOVE 3 TO F-LEN. MOVE "XYZ" TO F-REC. REWRITE F-REC.',
            '    DISPLAY "RW " ST.',
            "    READ F. DISPLAY F-LEN.",
            "    CLOSE F.",
            "    OPEN OUTPUT R.",
            '    MOVE "WXYZ" TO R-REC.',
            "    MOVE 2 TO R-LEN. WRITE R-REC.",
            "    MOVE 4 TO R-LEN. WRITE R-REC.",
            "    CLOSE R.",
            "    OPEN INPUT R.",
            "    READ R. DISPLAY R-LEN RK.",
            "    READ R. DISPLAY R-LEN RK.",
            "    CLOSE R.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=50000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            path_overrides={"F": tmp_path / "vsq", "R": tmp_path / "vrl"},
        ),
    )
    assert (
        capsys.readouterr().out,
        (tmp_path / "vsq").read_bytes(),
        (tmp_path / "vrl").read_bytes(),
    ) == (
        "W 44\nW 44\n03 [ABC  ]\nRW 44\nRW 00\n05\n21\n42\n",
        b"\x00\x07\x00\x00\xe7\xe8\xe9\x00\x09\x00\x00\xc1\xc2\xc3\xc4\xc5",
        b"\x00\x06\x00\x00\xe6\xe7\x00\x00\x00\x08\x00\x00\xe6\xe7\xe8\xe9",
    )
