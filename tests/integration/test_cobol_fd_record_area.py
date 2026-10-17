"""Every 01 under one FD describes the same record area, and each FD has its own:
a MOVE to one record of a file is what WRITE of another record of that file
sends, and records of different files never share storage."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import to_fixed

_LINES = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RECAREA.",
    "ENVIRONMENT DIVISION.",
    "INPUT-OUTPUT SECTION.",
    "FILE-CONTROL.",
    "    SELECT PRINT-FILE ASSIGN TO PRTDD",
    "        ORGANIZATION IS SEQUENTIAL.",
    "    SELECT DATA-FILE ASSIGN TO DATDD",
    "        ORGANIZATION IS SEQUENTIAL.",
    "DATA DIVISION.",
    "FILE SECTION.",
    "FD  PRINT-FILE.",
    "01  PRINT-REC        PIC X(10).",
    "01  DUMMY-RECORD     PIC X(10).",
    "FD  DATA-FILE.",
    "01  DATA-REC         PIC X(10).",
    "WORKING-STORAGE SECTION.",
    "01  WS-DUMMY         PIC X.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
    "    OPEN OUTPUT PRINT-FILE DATA-FILE.",
    '    MOVE "HELLO" TO PRINT-REC.',
    '    MOVE "WORLD" TO DATA-REC.',
    "    WRITE DUMMY-RECORD.",
    "    WRITE DATA-REC.",
    "    CLOSE PRINT-FILE DATA-FILE.",
    "    STOP RUN.",
]


@covers(CobolFeature.WRITE)
def test_records_of_one_fd_share_its_area_and_fds_do_not_overlap(
    tmp_path: Path,
) -> None:
    print_path = tmp_path / "prtdd.dat"
    data_path = tmp_path / "datdd.dat"
    provider = RealFileIOProvider(
        base_dir=tmp_path,
        file_control=[],
        path_overrides={"PRINT-FILE": print_path, "DATA-FILE": data_path},
    )
    run(to_fixed(_LINES), language="cobol", io_provider=provider, max_steps=50_000)

    assert (print_path.read_bytes(), data_path.read_bytes()) == (
        bytes(EbcdicTable.ascii_to_ebcdic(b"HELLO     ")),
        bytes(EbcdicTable.ascii_to_ebcdic(b"WORLD     ")),
    )
