"""End-to-end: ACCEPT from the system input device reads fixed-length records."""

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


@covers(CobolFeature.ACCEPT)
def test_accept_concatenates_records_and_stores_them_unedited(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ACCSYS.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 LONG-AREA PIC X(10).",
            "01 SHORT-AREA PIC X(2).",
            "01 DIGITS-9 PIC 9(9).",
            "01 DIGITS-4 PIC 9(4).",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    ACCEPT LONG-AREA.",
            "    ACCEPT SHORT-AREA.",
            "    ACCEPT DIGITS-9.",
            "    ACCEPT DIGITS-4.",
            "    DISPLAY LONG-AREA SHORT-AREA DIGITS-9 DIGITS-4.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=5000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            system_input=["ABCD", "EFGH", "IJKL", "MNOP", "0123456789", "12  "],
        ),
    )
    assert capsys.readouterr().out == "ABCDEFGHIJMN01234567812  "
