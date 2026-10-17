"""End-to-end: SORT orders a sort file's records by its keys between the USING and
GIVING files."""

from __future__ import annotations

from collections.abc import Sequence
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
            path_overrides={name: tmp_path / name for name in _FILES},
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
