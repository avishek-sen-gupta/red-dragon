"""End-to-end: GO TO a section name enters the section at its first paragraph."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
    ws_region,
)
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode,
)


def _pgm(goto: str) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. GOSECT.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-IDX PIC 9 VALUE 2.",
        "01 WS-T   PIC 9(4) VALUE 0.",
        "PROCEDURE DIVISION.",
        "MAIN SECTION.",
        "M1.",
        "    COMPUTE WS-T = WS-T * 10 + 1.",
        f"    {goto}.",
        "    COMPUTE WS-T = WS-T * 10 + 9.",
        "SEC2 SECTION.",
        "S1.",
        "    COMPUTE WS-T = WS-T * 10 + 2.",
        "SEC3 SECTION.",
        "S3.",
        "    COMPUTE WS-T = WS-T * 10 + 3.",
        "    STOP RUN.",
    ]


@pytest.mark.usefixtures("bridge_jar")
class TestGotoSection:
    @pytest.mark.parametrize(
        "goto,expected",
        [
            ("GO TO SEC2", 123),
            ("GO TO S1 SEC3 DEPENDING ON WS-IDX", 13),
        ],
    )
    @covers(CobolFeature.GO_TO, CobolFeature.GOTO_DEPENDING_ON)
    def test_goto_section_runs_section_then_falls_through(
        self, goto: str, expected: int
    ):
        vm = run_cobol(_pgm(goto), max_steps=2000)
        assert _decode(ws_region(vm, "GOSECT"), 1, 4) == expected
