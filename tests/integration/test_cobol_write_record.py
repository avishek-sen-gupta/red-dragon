# pyright: standard
"""WRITE record-name (no FROM) must flush the record's contents, not its name.

Regression for red-dragon-m0oa.6: `WRITE OUT-REC` used to write the literal
string "OUT-REC" instead of the value MOVE'd into the record area.
"""

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
    "PROGRAM-ID. WRTEST.",
    "ENVIRONMENT DIVISION.",
    "INPUT-OUTPUT SECTION.",
    "FILE-CONTROL.",
    "    SELECT OUT-FILE ASSIGN TO OUTDD",
    "        ORGANIZATION IS SEQUENTIAL.",
    "DATA DIVISION.",
    "FILE SECTION.",
    "FD  OUT-FILE.",
    "01  OUT-REC          PIC X(5).",
    "WORKING-STORAGE SECTION.",
    "01  WS-DUMMY         PIC X.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
    "    OPEN OUTPUT OUT-FILE.",
    '    MOVE "HELLO" TO OUT-REC.',
    "    WRITE OUT-REC.",
    "    CLOSE OUT-FILE.",
    "    STOP RUN.",
]


class TestWriteRecordContents:
    @covers(CobolFeature.WRITE)
    def test_write_flushes_record_contents_not_name(self, tmp_path: Path) -> None:
        out_path = tmp_path / "outdd.dat"
        provider = RealFileIOProvider(
            base_dir=tmp_path,
            file_control=[],
            path_overrides={"OUT-FILE": out_path},
        )
        vm = run(
            to_fixed(_LINES),
            language="cobol",
            io_provider=provider,
            max_steps=50_000,
        )
        assert vm is not None
        assert out_path.exists(), "OUT-FILE was never written"
        data = out_path.read_bytes()
        # Byte-faithful WRITE: the file holds the record's raw EBCDIC bytes
        # (red-dragon-zwzg), not ASCII and not the record name.
        assert (
            bytes(EbcdicTable.ascii_to_ebcdic(b"HELLO")) in data
        ), f"record contents not written; got {data!r}"
        assert (
            bytes(EbcdicTable.ascii_to_ebcdic(b"OUT-REC")) not in data
        ), "WRITE wrote the record NAME, not its contents"
