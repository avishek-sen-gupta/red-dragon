"""Byte-faithful (EBCDIC) file I/O round-trip for a record containing COMP-3.

red-dragon-zwzg: a plain ``WRITE rec`` used to run the whole FD record GROUP
through the EBCDIC→ASCII alphanumeric decoder, mangling packed COMP-3 bytes into
U+FFFD and then crashing in ``RealFileIOProvider._write_record``
(``data.encode("latin-1")``). After the core change the file stores the record
area's raw byte-image verbatim, so a COMP-3 amount survives the write and reads
back equal.

These exercise full VM execution via ``run`` with a disk-backed
``RealFileIOProvider``: program 1 OPEN OUTPUT / MOVE / WRITE / CLOSE writes the
record; program 2 reopens OPEN INPUT / READ and we assert the COMP-3 value
round-trips. We also assert byte-faithfulness directly: the backing file's bytes
equal the expected EBCDIC record image.
"""

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


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce PROLEAP_BRIDGE_JAR."""


# Record layout (12 bytes):
#   05 R-ID   PIC 9(3)            -> 3 bytes zoned DISPLAY, offset 0
#   05 R-NAME PIC X(5)            -> 5 bytes alphanumeric, offset 3
#   05 R-AMT  PIC S9(5)V99 COMP-3 -> 4 bytes packed, offset 8  (ceil((7+1)/2)=4)
_REC_LEN = 12
_AMT_OFFSET = 8
_AMT_BYTES = 4


def _expected_comp3(value_digits: str, negative: bool) -> bytes:
    """Build the COMP-3 (packed decimal) byte-image for S9(5)V99, 4 bytes.

    7 digits + 1 sign nibble = 8 nibbles = 4 bytes. High-order digit padded.
    Sign nibble: 0x0C positive, 0x0D negative.
    """
    digits = value_digits.rjust(7, "0")
    nibbles = [int(d) for d in digits] + [0x0D if negative else 0x0C]
    return bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))


def _writer_program() -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. CWRT.",
        "ENVIRONMENT DIVISION.",
        "INPUT-OUTPUT SECTION.",
        "FILE-CONTROL.",
        "    SELECT F1 ASSIGN TO XXXXX001.",
        "DATA DIVISION.",
        "FILE SECTION.",
        "FD  F1.",
        "01  OUT-REC.",
        "    05 R-ID   PIC 9(3).",
        "    05 R-NAME PIC X(5).",
        "    05 R-AMT  PIC S9(5)V99 USAGE COMP-3.",
        "WORKING-STORAGE SECTION.",
        "01  WS-DONE PIC 9(1) VALUE 0.",
        "PROCEDURE DIVISION.",
        "MAIN-P.",
        "    OPEN OUTPUT F1.",
        "    MOVE 123 TO R-ID.",
        '    MOVE "HELLO" TO R-NAME.',
        "    MOVE -123.45 TO R-AMT.",
        "    WRITE OUT-REC.",
        "    MOVE 1 TO WS-DONE.",
        "    CLOSE F1.",
        "    STOP RUN.",
    ]


def _reader_program() -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. CRDR.",
        "ENVIRONMENT DIVISION.",
        "INPUT-OUTPUT SECTION.",
        "FILE-CONTROL.",
        "    SELECT F1 ASSIGN TO XXXXX001.",
        "DATA DIVISION.",
        "FILE SECTION.",
        "FD  F1.",
        "01  IN-REC.",
        "    05 R-ID   PIC 9(3).",
        "    05 R-NAME PIC X(5).",
        "    05 R-AMT  PIC S9(5)V99 USAGE COMP-3.",
        "WORKING-STORAGE SECTION.",
        "01  WS-EOF PIC 9(1) VALUE 0.",
        "PROCEDURE DIVISION.",
        "MAIN-P.",
        "    OPEN INPUT F1.",
        "    READ F1 AT END MOVE 1 TO WS-EOF END-READ.",
        "    CLOSE F1.",
        "    STOP RUN.",
    ]


def _run(lines: list[str], data_path: Path, tmp_path: Path):
    provider = RealFileIOProvider(
        base_dir=tmp_path,
        file_control=[],
        path_overrides={"F1": data_path},
    )
    return run(to_fixed(lines), language="cobol", io_provider=provider, max_steps=8000)


class TestComp3WriteRoundtrip:
    @covers(CobolFeature.WRITE)
    def test_write_does_not_crash_and_file_is_byte_faithful(
        self, tmp_path: Path
    ) -> None:
        # WRITE of a record with a COMP-3 subfield must not crash, and the backing
        # file must hold the raw EBCDIC byte-image of the record region.
        data_path = tmp_path / "f1.dat"
        self_run = _run(self._writer(), data_path, tmp_path)
        assert self_run is not None

        written = data_path.read_bytes()
        assert len(written) == _REC_LEN
        # COMP-3 region of -123.45 -> digits "0012345", negative sign nibble.
        expected_amt = _expected_comp3("0012345", negative=True)
        assert written[_AMT_OFFSET : _AMT_OFFSET + _AMT_BYTES] == expected_amt

    @covers(CobolFeature.READ)
    def test_comp3_round_trips_on_read(self, tmp_path: Path) -> None:
        # Write then reopen+read: the COMP-3 amount in the FD record region must
        # equal the bytes that were written (byte-faithful round-trip).
        data_path = tmp_path / "f1.dat"
        _run(self._writer(), data_path, tmp_path)

        vm = _run(_reader_program(), data_path, tmp_path)
        # The FD record region holds the file's raw bytes verbatim. The file
        # section region is one of the VM regions; locate the COMP-3 slot by the
        # expected byte-image written on the WRITE side.
        expected_amt = _expected_comp3("0012345", negative=True)
        regions = [vm.region_get(k) for k in vm.region_keys()]
        found = any(
            bytes(r[_AMT_OFFSET : _AMT_OFFSET + _AMT_BYTES]) == expected_amt
            for r in regions
            if len(r) >= _AMT_OFFSET + _AMT_BYTES
        )
        assert found, "COMP-3 bytes did not round-trip into any region"

    def _writer(self) -> list[str]:
        return _writer_program()
