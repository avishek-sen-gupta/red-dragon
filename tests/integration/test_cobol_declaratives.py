# pyright: standard
"""End-to-end: DECLARATIVES must not be the program entry point (red-dragon-m0oa.3)."""

from __future__ import annotations

from pathlib import Path

from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import to_fixed

# A program whose DECLARATIVES USE section writes "DECL" and whose real body
# (after END DECLARATIVES) writes "MAIN". Correct COBOL starts at MAIN-PARA,
# so the output file must contain MAIN and never DECL.
_SRC = to_fixed(
    [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. DECLTEST.",
        "ENVIRONMENT DIVISION.",
        "INPUT-OUTPUT SECTION.",
        "FILE-CONTROL.",
        "    SELECT OUT-FILE ASSIGN TO OUTDD",
        "        ORGANIZATION IS SEQUENTIAL.",
        "DATA DIVISION.",
        "FILE SECTION.",
        "FD  OUT-FILE.",
        "01  OUT-REC          PIC X(4).",
        "WORKING-STORAGE SECTION.",
        "01  WS-LINE          PIC X(4).",
        "PROCEDURE DIVISION.",
        "DECLARATIVES.",
        "ERR-SECTION SECTION.",
        "    USE AFTER STANDARD ERROR PROCEDURE ON OUT-FILE.",
        "ERR-PARA.",
        '    MOVE "DECL" TO OUT-REC.',
        "    WRITE OUT-REC.",
        "END DECLARATIVES.",
        "MAIN SECTION.",
        "MAIN-PARA.",
        "    OPEN OUTPUT OUT-FILE.",
        '    MOVE "MAIN" TO OUT-REC.',
        "    WRITE OUT-REC.",
        "    CLOSE OUT-FILE.",
        "    STOP RUN.",
    ]
)


class TestDeclarativesEntryPoint:
    @covers(CobolFeature.DECLARATIVES)
    def test_entry_point_skips_declaratives(self, tmp_path: Path) -> None:
        out_path = tmp_path / "outdd.dat"
        provider = RealFileIOProvider(
            base_dir=tmp_path,
            file_control=[],
            path_overrides={"OUT-FILE": out_path},
        )
        result = run(_SRC, language="cobol", io_provider=provider, max_steps=50_000)
        assert result is not None
        assert out_path.exists(), "OUT-FILE was never written — entry point wrong"
        # Byte-faithful WRITE: the file holds raw EBCDIC bytes (red-dragon-zwzg).
        data = out_path.read_bytes()
        assert bytes(EbcdicTable.ascii_to_ebcdic(b"MAIN")) in data
        assert bytes(EbcdicTable.ascii_to_ebcdic(b"DECL")) not in data
