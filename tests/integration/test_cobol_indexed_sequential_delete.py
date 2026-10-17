"""End-to-end: a sequential READ after a DELETE of the current indexed record
returns the record that followed it."""

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


@covers(CobolFeature.DELETE_RECORD)
@covers(CobolFeature.READ)
def test_reading_on_after_a_delete_skips_no_record(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. IXDEL.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT IX ASSIGN TO "ixf" ORGANIZATION IS INDEXED',
            "        ACCESS MODE IS SEQUENTIAL RECORD KEY IS IX-KEY",
            "        FILE STATUS IS ST.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD IX.",
            "01 IX-REC.",
            "   05 IX-KEY PIC X.",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IX.",
            '    MOVE "A" TO IX-KEY. WRITE IX-REC.',
            '    MOVE "B" TO IX-KEY. WRITE IX-REC.',
            '    MOVE "C" TO IX-KEY. WRITE IX-REC.',
            '    MOVE "D" TO IX-KEY. WRITE IX-REC.',
            "    CLOSE IX.",
            "    OPEN I-O IX.",
            "    READ IX. DELETE IX. READ IX. DISPLAY IX-KEY.",
            "    READ IX. DELETE IX. READ IX. DISPLAY IX-KEY.",
            "    READ IX. DISPLAY ST.",
            "    CLOSE IX.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=20000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path, path_overrides={"IX": tmp_path / "ixf"}
        ),
    )
    assert (capsys.readouterr().out, (tmp_path / "ixf").read_bytes()) == (
        "B\nD\n10\n",
        b"\xc2\xc4",
    )
