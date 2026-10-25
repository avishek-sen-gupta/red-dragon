"""End-to-end: SORT orders a sort file's records by its keys between the USING and
GIVING files."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.record_io.run_inputs import RunInputs
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    to_fixed,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")

_FILES = ("IN-F", "OUT-F", "SRT")

_MIXED_FIELDS = (
    "PIC X.",
    "PIC S9(3) COMP-3.",
    "PIC S9(4) COMP.",
    "PIC S9(2) SIGN LEADING SEPARATE.",
    "PIC S99.",
    "PIC X.",
)


def _record(level01: str, prefix: str, pictures: Sequence[str]) -> list[str]:
    return [
        f"01 {level01}.",
        *(f"    05 {prefix}-{n} {pic}" for n, pic in enumerate(pictures, start=1)),
    ]


def _program(
    pictures: Sequence[str],
    writes: Sequence[str],
    sort: Sequence[str],
    records: int,
) -> str:
    return to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. SORTP.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            *(f'    SELECT {name} ASSIGN TO "{name}".' for name in _FILES),
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD IN-F.",
            *_record("IN-REC", "I", pictures),
            "FD OUT-F.",
            *_record("OUT-REC", "O", pictures),
            "SD SRT.",
            *_record("SRT-REC", "S", pictures),
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IN-F.",
            *writes,
            "    CLOSE IN-F.",
            *sort,
            "    OPEN INPUT OUT-F.",
            *(f"    READ OUT-F. DISPLAY O-{len(pictures)}." for _ in range(records)),
            "    CLOSE OUT-F.",
            "    STOP RUN.",
        ]
    )


def _sorted_output(
    source: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> str:
    run(
        source=source,
        language="cobol",
        max_steps=50000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(path_overrides={name: tmp_path / name for name in _FILES}),
        ),
    )
    return capsys.readouterr().out


def _write(values: Sequence[str]) -> list[str]:
    return [
        *(f"    MOVE {value} TO I-{n}." for n, value in enumerate(values, start=1)),
        "    WRITE IN-REC.",
    ]


@covers(CobolFeature.SORT)
def test_sort_using_giving_orders_by_key_keeping_equal_keys_in_input_order(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    inputs = (("CCC", "1"), ("AAA", "2"), ("BBB", "3"), ("AAA", "4"))
    source = _program(
        ("PIC X(3).", "PIC X."),
        [line for key, tag in inputs for line in _write((f'"{key}"', f'"{tag}"'))],
        ["    SORT SRT ON ASCENDING KEY S-1 USING IN-F GIVING OUT-F."],
        len(inputs),
    )
    assert _sorted_output(source, tmp_path, capsys) == "2\n4\n3\n1\n"


@covers(CobolFeature.SORT)
def test_sort_keys_of_every_usage_order_major_to_minor_each_in_its_direction(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    inputs = (
        ('"A"', "5", "1", "0", "0", '"1"'),
        ('"A"', "-5", "-9", "0", "0", '"2"'),
        ('"A"', "5", "-1", "0", "0", '"3"'),
        ('"A"', "5", "-1", "-3", "0", '"4"'),
        ('"A"', "5", "-1", "-3", "7", '"5"'),
        ('"B"', "-99", "0", "0", "0", '"6"'),
        ('"0"', "0", "0", "0", "0", '"7"'),
    )
    source = _program(
        _MIXED_FIELDS,
        [line for values in inputs for line in _write(values)],
        [
            "    SORT SRT ON ASCENDING KEY S-1 DESCENDING S-2",
            "        ASCENDING S-3 S-4 DESCENDING KEY S-5",
            "        USING IN-F GIVING OUT-F.",
        ],
        len(inputs),
    )
    assert _sorted_output(source, tmp_path, capsys) == "5\n4\n3\n1\n2\n6\n7\n"


@covers(CobolFeature.SORT_PROCEDURE)
def test_sort_procedures_release_and_return_the_records_in_key_order(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. SORTPROC.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            '    SELECT SRT ASSIGN TO "SRT".',
            "DATA DIVISION.",
            "FILE SECTION.",
            "SD SRT.",
            "01 SRT-REC.",
            "    05 S-1 PIC X.",
            "    05 S-2 PIC X.",
            "WORKING-STORAGE SECTION.",
            '01 WS-A PIC XX VALUE "A2".',
            '01 WS-B PIC XX VALUE "B4".',
            "01 WS-OUT PIC XX.",
            '01 EOF-FLAG PIC X VALUE "N".',
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    SORT SRT ON DESCENDING KEY S-1 INPUT PROCEDURE IS FEED",
            "        OUTPUT PROCEDURE IS SHOW-1 THRU SHOW-2.",
            '    DISPLAY "END".',
            "    STOP RUN.",
            "SHOW-1.",
            "    RETURN SRT INTO WS-OUT",
            '        AT END MOVE "Y" TO EOF-FLAG DISPLAY "AT END"',
            '        NOT AT END DISPLAY WS-OUT " " SRT-REC',
            "    END-RETURN.",
            '    IF EOF-FLAG = "N" GO TO SHOW-1.',
            "SHOW-2.",
            '    DISPLAY "DRAINED".',
            "FEED SECTION.",
            "FEED-1.",
            '    MOVE "B1" TO SRT-REC.',
            "    RELEASE SRT-REC.",
            "    RELEASE SRT-REC FROM WS-A.",
            '    MOVE "C3" TO SRT-REC.',
            "    RELEASE SRT-REC.",
            "    RELEASE SRT-REC FROM WS-B.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=50000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(path_overrides={"SRT": tmp_path / "SRT"}),
        ),
    )
    assert capsys.readouterr().out == (
        "C3 C3\nB1 B1\nB4 B4\nA2 A2\nAT END\nDRAINED\nEND\n"
    )


@covers(CobolFeature.MERGE)
def test_merge_interleaves_ordered_files_with_equal_keys_in_using_order(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    files = ("IN-F", "IN-G", "OUT-F", "SRT")
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. MERGEP.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            *(f'    SELECT {name} ASSIGN TO "{name}".' for name in files),
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD IN-F.",
            "01 F-REC PIC XX.",
            "FD IN-G.",
            "01 G-REC PIC XX.",
            "FD OUT-F.",
            "01 OUT-REC PIC XX.",
            "SD SRT.",
            "01 SRT-REC.",
            "    05 S-KEY PIC X.",
            "    05 S-TAG PIC X.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IN-F IN-G.",
            '    MOVE "A1" TO F-REC. WRITE F-REC.',
            '    MOVE "C2" TO F-REC. WRITE F-REC.',
            '    MOVE "A3" TO G-REC. WRITE G-REC.',
            '    MOVE "B4" TO G-REC. WRITE G-REC.',
            "    CLOSE IN-F IN-G.",
            "    MERGE SRT ON ASCENDING KEY S-KEY USING IN-G IN-F",
            "        GIVING OUT-F.",
            "    OPEN INPUT OUT-F.",
            *("    READ OUT-F. DISPLAY OUT-REC." for _ in range(4)),
            "    CLOSE OUT-F.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=50000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(path_overrides={name: tmp_path / name for name in files}),
        ),
    )
    assert capsys.readouterr().out == "A3\nA1\nB4\nC2\n"


@covers(CobolFeature.SORT)
def test_sort_collates_by_its_collating_sequence_else_the_programs(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    files = ("IN-F", "SRT")
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. SORTCOLL.",
            "ENVIRONMENT DIVISION.",
            "CONFIGURATION SECTION.",
            "OBJECT-COMPUTER. X PROGRAM COLLATING SEQUENCE IS ASC.",
            "SPECIAL-NAMES.",
            "    ALPHABET ASC IS STANDARD-1",
            "    ALPHABET NAT IS NATIVE.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            *(f'    SELECT {name} ASSIGN TO "{name}".' for name in files),
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD IN-F.",
            "01 IN-REC PIC X.",
            "SD SRT.",
            "01 SRT-REC PIC X.",
            "WORKING-STORAGE SECTION.",
            '01 EOF-FLAG PIC X VALUE "N".',
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IN-F.",
            '    MOVE "A" TO IN-REC. WRITE IN-REC.',
            '    MOVE "1" TO IN-REC. WRITE IN-REC.',
            "    CLOSE IN-F.",
            "    SORT SRT ON ASCENDING KEY SRT-REC USING IN-F",
            "        OUTPUT PROCEDURE SHOW.",
            '    MOVE "N" TO EOF-FLAG.',
            "    SORT SRT ON ASCENDING KEY SRT-REC",
            "        COLLATING SEQUENCE IS NAT USING IN-F",
            "        OUTPUT PROCEDURE SHOW.",
            "    STOP RUN.",
            "SHOW.",
            '    RETURN SRT AT END MOVE "Y" TO EOF-FLAG',
            "        NOT AT END DISPLAY SRT-REC END-RETURN.",
            '    IF EOF-FLAG = "N" GO TO SHOW.',
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=50000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(path_overrides={name: tmp_path / name for name in files}),
        ),
    )
    assert capsys.readouterr().out == "1\nA\nA\n1\n"


@covers(CobolFeature.MERGE)
def test_merge_using_a_missing_file_merges_the_files_that_opened(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    files = ("IN-F", "MISS-F", "SRT")
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. MERGEMIS.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            *(f'    SELECT {name} ASSIGN TO "{name}".' for name in files[:2]),
            '    SELECT SRT ASSIGN TO "SRT".',
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD IN-F.",
            "01 F-REC PIC XX.",
            "FD MISS-F.",
            "01 M-REC PIC XX.",
            "SD SRT.",
            "01 SRT-REC.",
            "    05 S-KEY PIC X.",
            "    05 S-TAG PIC X.",
            "WORKING-STORAGE SECTION.",
            '01 EOF-FLAG PIC X VALUE "N".',
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IN-F.",
            '    MOVE "A1" TO F-REC. WRITE F-REC.',
            '    MOVE "C2" TO F-REC. WRITE F-REC.',
            "    CLOSE IN-F.",
            "    MERGE SRT ON ASCENDING KEY S-KEY USING MISS-F IN-F",
            "        OUTPUT PROCEDURE IS SHOW.",
            '    DISPLAY "END".',
            "    STOP RUN.",
            "SHOW.",
            '    RETURN SRT AT END MOVE "Y" TO EOF-FLAG DISPLAY "AT END"',
            "        NOT AT END DISPLAY SRT-REC END-RETURN.",
            '    IF EOF-FLAG = "N" GO TO SHOW.',
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=50000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(path_overrides={name: tmp_path / name for name in files}),
        ),
    )
    assert capsys.readouterr().out == "A1\nC2\nAT END\nEND\n"


@covers(CobolFeature.SORT)
def test_sort_of_variable_length_records_keeps_each_record_its_own_size(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    files = ("IN-F", "OUT-F", "SRT")
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. SORTVAR.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            *(f'    SELECT {name} ASSIGN TO "{name}".' for name in files),
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD IN-F RECORD IS VARYING IN SIZE.",
            "01 IN-SHORT PIC X(3).",
            "01 IN-LONG PIC X(8).",
            "FD OUT-F RECORD IS VARYING IN SIZE.",
            "01 OUT-SHORT PIC X(3).",
            "01 OUT-LONG PIC X(8).",
            "SD SRT RECORD IS VARYING IN SIZE.",
            "01 S-SHORT.",
            "    05 S-KEY PIC X.",
            "    05 FILLER PIC XX.",
            "01 S-LONG PIC X(8).",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IN-F.",
            '    MOVE "BLONGREC" TO IN-LONG. WRITE IN-LONG.',
            '    MOVE "ASH" TO IN-SHORT. WRITE IN-SHORT.',
            '    MOVE "CLONGXYZ" TO IN-LONG. WRITE IN-LONG.',
            "    CLOSE IN-F.",
            "    SORT SRT ON ASCENDING KEY S-KEY USING IN-F GIVING OUT-F.",
            "    OPEN INPUT OUT-F.",
            *(
                '    MOVE ALL "*" TO OUT-LONG. READ OUT-F. DISPLAY OUT-LONG.'
                for _ in range(3)
            ),
            '    READ OUT-F AT END DISPLAY "EOF".',
            "    CLOSE OUT-F.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=50000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            inputs=RunInputs(path_overrides={name: tmp_path / name for name in files}),
        ),
    )
    assert capsys.readouterr().out == "ASH*****\nBLONGREC\nCLONGXYZ\nEOF\n"
