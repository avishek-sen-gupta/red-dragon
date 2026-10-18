"""End-to-end: an indexed file's prime key is found where it lies in that file's own
record, whatever FDs come before it."""

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


@covers(CobolFeature.WRITE)
@covers(CobolFeature.READ)
def test_a_later_fds_record_key_is_found_in_its_own_record(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. IXOFF.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT P ASSIGN TO "pf".',
            '    SELECT IX ASSIGN TO "ixf" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS DYNAMIC RECORD KEY IS IX-KEY",
            "        FILE STATUS IS ST.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD P.",
            "01 P-REC PIC X(10).",
            "FD IX.",
            "01 IX-REC.",
            "   05 IX-TAG PIC X.",
            "   05 IX-KEY PIC 9.",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IX.",
            '    MOVE "C3" TO IX-REC. WRITE IX-REC. DISPLAY ST.',
            '    MOVE "A1" TO IX-REC. WRITE IX-REC. DISPLAY ST.',
            '    MOVE "B2" TO IX-REC. WRITE IX-REC. DISPLAY ST.',
            "    CLOSE IX.",
            "    OPEN INPUT IX.",
            "    READ IX NEXT. DISPLAY ST IX-REC.",
            "    READ IX NEXT. DISPLAY ST IX-REC.",
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
    assert (capsys.readouterr().out, (tmp_path / "ixf").read_bytes()) == (
        "00\n00\n00\n00A1\n00B2\n",
        b"\xc1\xf1\xc2\xf2\xc3\xf3",
    )
