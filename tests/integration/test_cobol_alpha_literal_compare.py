"""Integration test: alphanumeric quoted literal comparison.

A COBOL alphanumeric literal `"10"` (quoted) must stay the STRING "10"
throughout the pipeline.  The bug was that ``parse_literal`` stripped the
quotes and then coerced `"10"` → int 10, causing a type-mismatch in
IF comparisons between PIC X fields and quoted digit strings.

Test: PIC X(2) VALUE "10" compared to the literal "10" must match (RESULT=1).
"""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,
    decode_zoned_unsigned as _decode,
    first_region as _first_region,
    run_cobol,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR for this test module."""


class TestAlphaLiteralCompare:
    @covers(CobolFeature.IF_ELSE, CobolFeature.VALUE_CLAUSE)
    def test_quoted_digit_string_stays_string(self):
        """A quoted literal '10' must be treated as alphanumeric, not int 10.

        01 X PIC X(2) VALUE '10'.   ← alphanumeric field holding the string "10"
        IF X = '10' ... MOVE 1 TO RESULT   ← must match because both are the string "10"
        """
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-ALPHA.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-X PIC X(2) VALUE '10'.",
                "01 WS-RESULT PIC 9(1) VALUE 9.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    IF WS-X = '10'",
                "        MOVE 1 TO WS-RESULT",
                "    ELSE",
                "        MOVE 9 TO WS-RESULT",
                "    END-IF.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        # WS-X is PIC X(2) at offset 0 (2 bytes), WS-RESULT is PIC 9(1) at offset 2
        result = _decode(region, 2, 1)
        assert result == 1, (
            f"Expected RESULT=1 (strings matched), got {result}. "
            "parse_literal is probably coercing quoted '10' to int 10."
        )
