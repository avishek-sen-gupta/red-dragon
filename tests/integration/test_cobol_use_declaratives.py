"""USE AFTER ERROR/EXCEPTION declaratives fire on an unhandled I/O error
(red-dragon-m0oa.4).

An INPUT-opened sequential file rejects a WRITE with status 48 (see
``SequentialDriver.write`` — not a write mode). With no explicit INVALID KEY /
AT END clause on the WRITE, the matching USE declarative section must fire. The
declarative sets a WS flag we then decode and assert on.

These exercise full VM execution via ``run`` with a disk-backed
``RealFileIOProvider`` (the default provider never reports I/O errors), covering
all reachable paths: named-file USE fires, GLOBAL USE fires, and no-USE no-op.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,
    decode_zoned_unsigned as _decode,
    first_region as _first_region,
    to_fixed,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce PROLEAP_BRIDGE_JAR."""


def _named_file_program() -> list[str]:
    # USE ON the file; an INPUT-mode WRITE -> status 48 -> USE fires -> sets FLAG=1.
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. USET.",
        "ENVIRONMENT DIVISION.",
        "INPUT-OUTPUT SECTION.",
        "FILE-CONTROL.",
        "    SELECT F1 ASSIGN TO XXXXX001.",
        "DATA DIVISION.",
        "FILE SECTION.",
        "FD  F1.",
        "01  F1-REC PIC X(10).",
        "WORKING-STORAGE SECTION.",
        "01  FLAG PIC 9(1) VALUE 0.",
        "PROCEDURE DIVISION.",
        "DECLARATIVES.",
        "D1 SECTION.",
        "    USE AFTER STANDARD ERROR PROCEDURE ON F1.",
        "D1-P.",
        "    MOVE 1 TO FLAG.",
        "END DECLARATIVES.",
        "MAIN SECTION.",
        "MAIN-P.",
        "    OPEN INPUT F1.",
        '    MOVE "ABC" TO F1-REC.',
        "    WRITE F1-REC.",
        "    CLOSE F1.",
        "    STOP RUN.",
    ]


def _flag(lines: list[str], tmp_path: Path, offset: int = 0) -> int:
    # FLAG is the only WS field here -> offset 0, length 1.
    # A pre-existing data file lets OPEN INPUT succeed, so the WRITE (status 48)
    # is the sole I/O error that triggers the USE.
    data_path = tmp_path / "f1.dat"
    data_path.write_bytes(b" " * 10)
    provider = RealFileIOProvider(
        base_dir=tmp_path,
        file_control=[],
        path_overrides={"F1": data_path},
    )
    vm = run(to_fixed(lines), language="cobol", io_provider=provider, max_steps=4000)
    return _decode(_first_region(vm), offset, 1)


class TestUseDeclaratives:
    @covers(CobolFeature.DECLARATIVES)
    def test_named_file_use_fires_on_error(self, tmp_path: Path) -> None:
        # INPUT-mode WRITE on F1 -> status 48 -> named-file USE fires -> FLAG=1.
        assert _flag(_named_file_program(), tmp_path) == 1

    @covers(CobolFeature.DECLARATIVES)
    def test_global_use_fires_when_no_named_match(self, tmp_path: Path) -> None:
        # USE GLOBAL ... ON F1 registers under use_global; an I/O error on F1
        # resolves via the global fallback. (Uses the GLOBAL keyword form.)
        lines = _named_file_program()
        i = lines.index("    USE AFTER STANDARD ERROR PROCEDURE ON F1.")
        lines[i] = "    USE GLOBAL AFTER STANDARD ERROR PROCEDURE ON F1."
        assert _flag(lines, tmp_path) == 1

    @covers(CobolFeature.DECLARATIVES)
    def test_no_use_no_change(self, tmp_path: Path) -> None:
        # Same program without DECLARATIVES: the I/O error must not crash; FLAG stays 0.
        lines = [
            l
            for l in _named_file_program()
            if l
            not in (
                "DECLARATIVES.",
                "D1 SECTION.",
                "    USE AFTER STANDARD ERROR PROCEDURE ON F1.",
                "D1-P.",
                "    MOVE 1 TO FLAG.",
                "END DECLARATIVES.",
            )
        ]
        assert _flag(lines, tmp_path) == 0

    @covers(CobolFeature.DECLARATIVES)
    def test_explicit_at_end_suppresses_use(self, tmp_path: Path) -> None:
        # READ past EOF with an explicit AT END clause AND a USE on the file:
        # the AT END branch runs (sets FLAG=2), the USE does NOT fire (would set FLAG=1).
        lines = [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. USEP.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            "    SELECT F1 ASSIGN TO XXXXX001.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD  F1.",
            "01  F1-REC PIC X(10).",
            "WORKING-STORAGE SECTION.",
            "01  FLAG PIC 9(1) VALUE 0.",
            "PROCEDURE DIVISION.",
            "DECLARATIVES.",
            "D1 SECTION.",
            "    USE AFTER STANDARD ERROR PROCEDURE ON F1.",
            "D1-P.",
            "    MOVE 1 TO FLAG.",
            "END DECLARATIVES.",
            "MAIN SECTION.",
            "MAIN-P.",
            "    OPEN OUTPUT F1.",
            "    CLOSE F1.",
            "    OPEN INPUT F1.",
            "    READ F1 AT END MOVE 2 TO FLAG END-READ.",
            "    CLOSE F1.",
            "    STOP RUN.",
        ]
        assert _flag(lines, tmp_path) == 2
