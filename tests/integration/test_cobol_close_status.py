"""CLOSE updates the FILE STATUS field (red-dragon-m0oa.8).

Before the fix, lower_close discarded the close result: it emitted
__cobol_close_file but never extracted __cobol_io_status nor called
emit_file_status_update. So FILE STATUS kept its prior value — after reading to
EOF (status "10"), a CLOSE left the status at "10", and programs that check it
(e.g. CBACT01C's 9000-ACCTFILE-CLOSE) saw a non-"00" status and ABENDed.

This reads a one-record file to EOF (FS="10"), then CLOSEs; the CLOSE must reset
FS to "00". RESULT=1 means FS="00" after CLOSE (fixed); RESULT=9 means it stayed
non-"00" (the bug).
"""

from pathlib import Path

import pytest

from interpreter.run import run
from tests.covers import covers, NotLanguageFeature
from tests.integration.cobol_helpers import (
    bridge_jar,
    decode_zoned_unsigned as _decode,
    first_region as _first_region,
    to_fixed,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR (fails loudly if unset)."""


def _program() -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. CLOSET.",
        "ENVIRONMENT DIVISION.",
        "INPUT-OUTPUT SECTION.",
        "FILE-CONTROL.",
        "    SELECT F1 ASSIGN TO F1DD",
        "           ORGANIZATION IS SEQUENTIAL",
        "           FILE STATUS IS FS.",
        "DATA DIVISION.",
        "FILE SECTION.",
        "FD  F1.",
        "01  F1-REC PIC X(5).",
        "WORKING-STORAGE SECTION.",
        "01  RESULT PIC 9 VALUE 0.",
        "01  FS     PIC XX.",
        "01  EOF-FLAG PIC X VALUE 'N'.",
        "PROCEDURE DIVISION.",
        "MAIN.",
        "    OPEN INPUT F1.",
        "    PERFORM UNTIL EOF-FLAG = 'Y'",
        "        READ F1 AT END MOVE 'Y' TO EOF-FLAG END-READ",
        "    END-PERFORM.",
        "    CLOSE F1.",
        "    IF FS = '00' MOVE 1 TO RESULT ELSE MOVE 9 TO RESULT.",
        "    STOP RUN.",
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_close_resets_file_status_to_00(tmp_path: Path) -> None:
    data = tmp_path / "f1.dat"
    data.write_bytes(b"HELLO")  # one 5-byte record -> second READ hits EOF (FS=10)
    from interpreter.cobol.real_file_provider import RealFileIOProvider

    provider = RealFileIOProvider(
        base_dir=tmp_path, file_control=[], path_overrides={"F1DD": data, "F1": data}
    )
    vm = run(
        to_fixed(_program()), language="cobol", io_provider=provider, max_steps=5000
    )
    # RESULT is the first WS field (offset 0, 1 digit).
    assert _decode(_first_region(vm), 0, 1) == 1
