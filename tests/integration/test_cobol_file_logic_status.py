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


@covers(CobolFeature.OPEN)
def test_open_extend_of_an_absent_file_fails_with_35(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. FEXT.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F ASSIGN TO "absent" FILE STATUS IS ST.',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F.",
            "01 F-REC PIC X(4).",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN EXTEND F. DISPLAY ST.",
            '    MOVE "AAAA" TO F-REC. WRITE F-REC. DISPLAY ST.',
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=5000,
        io_provider=RealFileIOProvider(base_dir=tmp_path),
    )
    assert (capsys.readouterr().out, (tmp_path / "absent").exists()) == (
        "35\n48\n",
        False,
    )


@covers(CobolFeature.CLOSE)
@covers(CobolFeature.OPEN)
def test_open_after_close_with_lock_fails_with_38(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. FLOCK.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F ASSIGN TO "lockf" FILE STATUS IS ST.',
            '    SELECT G ASSIGN TO "freeg" FILE STATUS IS GS.',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F.",
            "01 F-REC PIC X(4).",
            "FD G.",
            "01 G-REC PIC X(4).",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "01 GS PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT F G.",
            "    CLOSE F WITH LOCK G. DISPLAY ST GS.",
            "    OPEN INPUT F G. DISPLAY ST GS.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=5000,
        io_provider=RealFileIOProvider(base_dir=tmp_path),
    )
    assert capsys.readouterr().out == "0000\n3800\n"


@covers(CobolFeature.DELETE_RECORD)
def test_delete_names_its_record_by_key_in_dynamic_access(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """ANSI X3.23-1985 Indexed I-O, DELETE: in random or dynamic access the
    record removed is the one the RECORD KEY names, with no prior READ; in
    sequential access it is the record last read, and 43 without one."""
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. DELKEY.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F ASSIGN TO "ixf" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS DYNAMIC RECORD KEY IS F-KEY",
            "        FILE STATUS IS ST.",
            '    SELECT G ASSIGN TO "ixg" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS SEQUENTIAL RECORD KEY IS G-KEY",
            "        FILE STATUS IS GT.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F.",
            "01 F-REC.",
            "   05 F-KEY PIC XX.",
            "   05 F-DATA PIC XX.",
            "FD G.",
            "01 G-REC.",
            "   05 G-KEY PIC XX.",
            "   05 G-DATA PIC XX.",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "01 GT PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT F G.",
            '    MOVE "01AA" TO F-REC G-REC. WRITE F-REC. WRITE G-REC.',
            '    MOVE "02BB" TO F-REC G-REC. WRITE F-REC. WRITE G-REC.',
            '    MOVE "03CC" TO F-REC G-REC. WRITE F-REC. WRITE G-REC.',
            "    CLOSE F G.",
            "    OPEN I-O F G.",
            '    MOVE "02" TO F-KEY. DELETE F. DISPLAY ST.',
            '    MOVE "09" TO F-KEY.',
            '    DELETE F INVALID KEY DISPLAY "INVALID " ST.',
            "    DELETE G. DISPLAY GT.",
            "    CLOSE F G.",
            "    OPEN INPUT F.",
            "    READ F NEXT. DISPLAY F-REC. READ F NEXT. DISPLAY F-REC.",
            "    READ F NEXT. DISPLAY ST.",
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
    assert capsys.readouterr().out == "00\nINVALID 23\n43\n01AA\n03CC\n10\n"
