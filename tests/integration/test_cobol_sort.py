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


def _program(
    sort_record: Sequence[str], inputs: Sequence[str], sort: Sequence[str]
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
            "01 IN-REC PIC X(6).",
            "FD OUT-F.",
            "01 OUT-REC PIC X(6).",
            "SD SRT.",
            *sort_record,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    OPEN OUTPUT IN-F.",
            *(f'    MOVE "{record}" TO IN-REC. WRITE IN-REC.' for record in inputs),
            "    CLOSE IN-F.",
            *sort,
            "    OPEN INPUT OUT-F.",
            *("    READ OUT-F. DISPLAY OUT-REC." for _ in inputs),
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
        max_steps=20000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path,
            path_overrides={name: tmp_path / name for name in _FILES},
        ),
    )
    return capsys.readouterr().out


@covers(CobolFeature.SORT)
def test_sort_using_giving_orders_by_key_keeping_equal_keys_in_input_order(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = _program(
        ["01 SRT-REC.", "    05 SRT-KEY PIC X(3).", "    05 SRT-TAG PIC X(3)."],
        ["CCC001", "AAA002", "BBB003", "AAA004"],
        ["    SORT SRT ON ASCENDING KEY SRT-KEY USING IN-F GIVING OUT-F."],
    )
    assert _sorted_output(source, tmp_path, capsys) == (
        "AAA002\nAAA004\nBBB003\nCCC001\n"
    )
