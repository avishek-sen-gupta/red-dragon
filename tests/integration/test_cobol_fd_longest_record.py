"""End-to-end: a file's record area is as long as its largest record, so a longer
record of the FD is written and read whole (its records differ in length, so the
file holds them behind record descriptor words)."""

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
def test_records_longer_than_the_first_are_kept_whole(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. FDAREA.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT F ASSIGN TO "fda".',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD F.",
            "01 F-SHORT PIC X(3).",
            "01 F-LONG.",
            "   05 F-HEAD PIC X(3).",
            "   05 F-TAIL PIC X(2).",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT F.",
            '    MOVE "ABCDE" TO F-LONG. WRITE F-LONG.',
            "    CLOSE F.",
            "    OPEN INPUT F.",
            '    MOVE SPACES TO F-LONG. READ F. DISPLAY "[" F-LONG "]".',
            "    CLOSE F.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=20000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path, inputs=RunInputs(path_overrides={"F": tmp_path / "fda"})
        ),
    )
    assert (capsys.readouterr().out, (tmp_path / "fda").read_bytes()) == (
        "[ABCDE]\n",
        b"\x00\x09\x00\x00\xc1\xc2\xc3\xc4\xc5",
    )
