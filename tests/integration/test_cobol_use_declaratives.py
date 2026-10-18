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

from collections.abc import Sequence
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
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode,
)
from tests.integration.cobol_helpers import (
    first_region as _first_region,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


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


def _flag(lines: Sequence[str], tmp_path: Path, offset: int = 0) -> int:
    # FLAG is the only WS field here -> offset 0, length 1.
    # A pre-existing data file lets OPEN INPUT succeed, so the WRITE (status 48)
    # is the sole I/O error that triggers the USE.
    data_path = tmp_path / "f1.dat"
    data_path.write_bytes(b" " * 10)
    provider = RealFileIOProvider(
        base_dir=tmp_path,
        inputs=RunInputs(file_control=[], path_overrides={"F1": data_path}),
    )
    vm = run(
        to_fixed(list(lines)), language="cobol", io_provider=provider, max_steps=4000
    )
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
        lines = [
            (
                "    USE GLOBAL AFTER STANDARD ERROR PROCEDURE ON F1."
                if line == "    USE AFTER STANDARD ERROR PROCEDURE ON F1."
                else line
            )
            for line in _named_file_program()
        ]
        assert _flag(lines, tmp_path) == 1

    @covers(CobolFeature.DECLARATIVES)
    def test_no_use_no_change(self, tmp_path: Path) -> None:
        # Same program without DECLARATIVES: the I/O error must not crash; FLAG stays 0.
        lines = [
            line
            for line in _named_file_program()
            if line
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
    def test_open_mode_use_fires(self, tmp_path: Path) -> None:
        lines = [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. USEM.",
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
            "    USE AFTER STANDARD ERROR PROCEDURE INPUT.",
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
        assert _flag(lines, tmp_path) == 1

    @covers(CobolFeature.DECLARATIVES)
    def test_multi_file_use_fires_for_second_file(self, tmp_path: Path) -> None:
        # USE ON F1 F2 with an I/O error on F2 (WRITE to INPUT-opened file -> status 48)
        # must fire the declarative. F2 is pre-created so OPEN INPUT succeeds (status 00);
        # the WRITE is the sole trigger.
        lines = [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. USEMF.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            "    SELECT F1 ASSIGN TO XXXXX001.",
            "    SELECT F2 ASSIGN TO XXXXX002.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD  F1.",
            "01  F1-REC PIC X(10).",
            "FD  F2.",
            "01  F2-REC PIC X(10).",
            "WORKING-STORAGE SECTION.",
            "01  FLAG PIC 9(1) VALUE 0.",
            "PROCEDURE DIVISION.",
            "DECLARATIVES.",
            "D1 SECTION.",
            "    USE AFTER STANDARD ERROR PROCEDURE ON F1 F2.",
            "D1-P.",
            "    MOVE 1 TO FLAG.",
            "END DECLARATIVES.",
            "MAIN SECTION.",
            "MAIN-P.",
            "    OPEN INPUT F2.",
            '    MOVE "ABC" TO F2-REC.',
            "    WRITE F2-REC.",
            "    CLOSE F2.",
            "    STOP RUN.",
        ]
        f2_path = tmp_path / "f2.dat"
        f2_path.write_bytes(b" " * 10)
        provider = RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(file_control=[], path_overrides={"F2": f2_path}),
        )
        vm = run(
            to_fixed(lines), language="cobol", io_provider=provider, max_steps=4000
        )
        assert _decode(_first_region(vm), 0, 1) == 1

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

    @covers(CobolFeature.DECLARATIVES)
    def test_open_mode_use_fires_for_the_mode_a_failed_open_attempted(
        self, tmp_path: Path
    ) -> None:
        # OPEN INPUT of an absent file fails with 35 and leaves F1 closed, so the
        # mode to match is the one OPEN attempted: the INPUT USE adds 1, the
        # OUTPUT USE never runs. A second OPEN INPUT fires it again, and OPEN
        # EXTEND of the absent file fires the EXTEND USE -> FLAG=5.
        lines = [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. USEO.",
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
            "    USE AFTER STANDARD ERROR PROCEDURE INPUT.",
            "D1-P.",
            "    ADD 1 TO FLAG.",
            "D2 SECTION.",
            "    USE AFTER STANDARD ERROR PROCEDURE OUTPUT.",
            "D2-P.",
            "    ADD 5 TO FLAG.",
            "D3 SECTION.",
            "    USE AFTER EXCEPTION PROCEDURE EXTEND.",
            "D3-P.",
            "    ADD 3 TO FLAG.",
            "END DECLARATIVES.",
            "MAIN SECTION.",
            "MAIN-P.",
            "    OPEN INPUT F1.",
            "    OPEN INPUT F1.",
            "    OPEN EXTEND F1.",
            "    STOP RUN.",
        ]
        provider = RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(
                file_control=[], path_overrides={"F1": tmp_path / "absent.dat"}
            ),
        )
        vm = run(
            to_fixed(lines), language="cobol", io_provider=provider, max_steps=4000
        )
        assert _decode(_first_region(vm), 0, 1) == 5

    @covers(CobolFeature.DECLARATIVES)
    def test_explicit_clause_leaves_other_statuses_to_use(self, tmp_path: Path) -> None:
        # AT END covers only the at-end condition (status class 1) and INVALID KEY
        # only class 2. A READ ... AT END of an unopened file (47) and a WRITE ...
        # INVALID KEY to a file open INPUT (48) still fire the USE: FLAG=2. The
        # READ past the end runs AT END only, adding nothing.
        lines = [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. USEC.",
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
            "    ADD 1 TO FLAG.",
            "END DECLARATIVES.",
            "MAIN SECTION.",
            "MAIN-P.",
            "    READ F1 AT END CONTINUE END-READ.",
            "    OPEN INPUT F1.",
            "    WRITE F1-REC INVALID KEY CONTINUE END-WRITE.",
            "    READ F1 AT END CONTINUE END-READ.",
            "    READ F1 AT END CONTINUE END-READ.",
            "    CLOSE F1.",
            "    STOP RUN.",
        ]
        assert _flag(lines, tmp_path) == 2
