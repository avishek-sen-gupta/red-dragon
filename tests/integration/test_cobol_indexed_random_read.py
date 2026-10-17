"""End-to-end: a random READ of an indexed file looks its record up by the prime
record key, or by the KEY phrase's data item, as bytes."""

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


@covers(CobolFeature.READ)
def test_a_random_read_finds_the_record_its_key_names(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. IXRAND.",
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
            "   05 IX-TAG PIC X.",
            "   05 IX-KEY PIC XX.",
            "WORKING-STORAGE SECTION.",
            "01 ST PIC XX.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IX.",
            '    MOVE "AK1" TO IX-REC. WRITE IX-REC.',
            '    MOVE "BK2" TO IX-REC. WRITE IX-REC.',
            '    MOVE "CK3" TO IX-REC. WRITE IX-REC.',
            "    CLOSE IX.",
            "    OPEN INPUT IX.",
            '    MOVE "K2" TO IX-KEY. READ IX. DISPLAY ST " " IX-REC.',
            '    MOVE "K9" TO IX-KEY. READ IX INVALID KEY DISPLAY "I " ST',
            "        END-READ.",
            '    MOVE "K3" TO IX-KEY. READ IX KEY IS IX-KEY.',
            '    DISPLAY ST " " IX-REC.',
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
    assert capsys.readouterr().out == "00 BK2\nI 23\n00 CK3\n"
