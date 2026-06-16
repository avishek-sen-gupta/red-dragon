# pyright: standard
"""READ ... AT END must terminate a sequential read loop at EOF (red-dragon-m0oa.7).

The file-status code returned by __cobol_io_status is a string ("10" at EOF),
but the comparison literal was lowered as a numeric const (int 10), so
`status == "10"` was always false and AT END never fired — an infinite read
loop. This is the dominant cause of NIST programs "halting" after the header.
"""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import to_fixed

_LINES = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RDLOOP.",
    "ENVIRONMENT DIVISION.",
    "INPUT-OUTPUT SECTION.",
    "FILE-CONTROL.",
    "    SELECT F ASSIGN TO FDD ORGANIZATION IS SEQUENTIAL.",
    "DATA DIVISION.",
    "FILE SECTION.",
    "FD  F.",
    "01  F-REC PIC 9(3).",
    "WORKING-STORAGE SECTION.",
    "01 WS-N PIC 9(3) VALUE 0.",
    "01 RDCOUNT PIC 9(4) VALUE 0.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
    "    OPEN OUTPUT F.",
    "WLOOP.",
    "    ADD 1 TO WS-N.",
    "    MOVE WS-N TO F-REC.",
    "    WRITE F-REC.",
    "    IF WS-N LESS THAN 3 GO TO WLOOP.",
    "    CLOSE F.",
    "    OPEN INPUT F.",
    "RLOOP.",
    "    READ F AT END GO TO DONE-PARA.",
    "    ADD 1 TO RDCOUNT.",
    "    GO TO RLOOP.",
    "DONE-PARA.",
    "    CLOSE F.",
    "    STOP RUN.",
]


class TestReadAtEndTerminates:
    @covers(CobolFeature.READ)
    def test_read_loop_stops_at_eof(self, tmp_path: Path) -> None:
        provider = RealFileIOProvider(
            base_dir=tmp_path,
            file_control=[],
            path_overrides={"F": tmp_path / "f.dat"},
        )
        # A correct run reads exactly 3 records then hits AT END and STOPs well
        # within this budget. An infinite loop would exhaust max_steps instead.
        vm = run(
            to_fixed(_LINES), language="cobol", io_provider=provider, max_steps=8000
        )
        assert vm is not None
        blob = b"".join(bytes(vm.region_get(k)) for k in vm.region_keys())
        # RDCOUNT is PIC 9(4); after reading 3 records it must equal 0003 (EBCDIC).
        assert (
            b"\xf0\xf0\xf0\xf3" in blob
        ), "RDCOUNT != 0003 — AT END did not terminate the read loop at EOF"
