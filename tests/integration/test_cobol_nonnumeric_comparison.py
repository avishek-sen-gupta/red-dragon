"""Integration: a relation with a nonnumeric operand compares characters, padded with spaces."""

from collections.abc import Sequence

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

_HEADER = (
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. CMPTEST.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 RES PIC X(20) VALUE SPACES.",
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR for this test module."""


def _outcomes(
    data: Sequence[str], setup: Sequence[str], conditions: Sequence[str]
) -> str:
    tests = [
        line
        for position, condition in enumerate(conditions, start=1)
        for line in (
            f"    IF {condition}",
            f"        MOVE 'Y' TO RES ({position}:1)",
            "    ELSE",
            f"        MOVE 'N' TO RES ({position}:1)",
            "    END-IF.",
        )
    ]
    vm = run_cobol(
        [*_HEADER, *data, "PROCEDURE DIVISION.", "MAIN-PARA.", *setup, *tests]
        + ["    STOP RUN."],
        max_steps=100_000,
    )
    return bytes(first_region(vm)[: len(conditions)]).decode("cp037")


class TestNonnumericComparison:
    @covers(CobolFeature.COMPARISON_OPERATORS, CobolFeature.IF_ELSE)
    def test_shorter_operand_is_padded_with_spaces(self):
        outcomes = _outcomes(
            [
                "01 XA PIC X(5) VALUE 'AB'.",
                "01 X1 PIC X VALUE 'X'.",
                "01 X5 PIC X(5) VALUE 'X'.",
                "01 X3 PIC X(3) VALUE 'AB'.",
                "01 E5 PIC -----.",
                "01 GRP.",
                "   02 GA PIC X(3) VALUE '1 1'.",
                "   02 GB PIC X(4) VALUE ' X'.",
            ],
            ["    MOVE -12 TO E5."],
            [
                'XA = "AB"',
                '"AB" = XA',
                'XA > "AB"',
                'XA NOT = "AB"',
                "X1 = X5",
                "X5 = X1",
                'X3 > "AB"',
                'X3 < "AB "',
                'XA < "ABC"',
                'XA = "AB      "',
                'E5 = "  -12 "',
                'GRP = "1 1 X"',
                "XA = SPACES",
            ],
        )
        assert outcomes == "YYNNYYNNYYYYN"

    @covers(CobolFeature.COMPARISON_OPERATORS, CobolFeature.IF_ELSE)
    def test_numeric_operand_against_nonnumeric_compares_its_digits(self):
        outcomes = _outcomes(
            [
                "01 X3 PIC X(3) VALUE '123'.",
                "01 ALN PIC X(6) VALUE '090109'.",
                "01 GRP.",
                "   02 GA PIC 99 VALUE 09.",
                "   02 GB PIC 9999 VALUE 0109.",
                "01 D6 PIC 9(6) VALUE 123456.",
                "01 N5 PIC 9(5) VALUE 12345.",
                "01 X9 PIC X(9) VALUE '12345'.",
                "01 S4 PIC S9(4) VALUE -1234.",
                "01 C4 PIC 9(4) COMP VALUE 42.",
                "01 X4 PIC X(4) VALUE '1234'.",
                "01 X40 PIC X(4) VALUE '0042'.",
            ],
            [],
            [
                "X3 = 123",
                "X3 > 123",
                "X3 < 124",
                "ALN = 090109",
                "ALN = 90109",
                "GRP = 090109",
                "D6 (3:) = 3456",
                "N5 = X9",
                "X9 = N5",
                "S4 = X4",
                "C4 = X40",
                "N5 = 12345",
                "N5 > 9999",
            ],
        )
        assert outcomes == "YNYYNYYYYYYYY"
