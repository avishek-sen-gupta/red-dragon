"""Integration tests for COBOL REDEFINES — complex scenarios.

These tests exercise the full REDEFINES pipeline:
COBOL source → ProLeap bridge → IR → CFG → VM execution.
They verify that REDEFINES creates proper aliases to the same memory region
and that writes/reads via either the original or alias see the same bytes.

Requires the ProLeap bridge JAR to be available (set PROLEAP_BRIDGE_JAR env var).
Tests skip gracefully when the JAR is absent.
"""

import os

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    JAR_PATH,
    JAR_AVAILABLE,
    first_region as _first_region,
    run_cobol as _run_cobol,
)

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


@pytest.fixture(autouse=True, scope="session")
def _set_bridge_jar_env():
    """Ensure PROLEAP_BRIDGE_JAR is set for the entire test session."""
    old = os.environ.get("PROLEAP_BRIDGE_JAR")
    os.environ["PROLEAP_BRIDGE_JAR"] = JAR_PATH
    yield
    if old is None:
        os.environ.pop("PROLEAP_BRIDGE_JAR", None)
    else:
        os.environ["PROLEAP_BRIDGE_JAR"] = old


def _ebcdic_to_ascii(region: list[int], offset: int, length: int) -> str:
    """Decode EBCDIC alphanumeric field to ASCII string.

    Maps common EBCDIC characters to ASCII:
    0x40 = space, 0xC1-0xC9 = A-I, 0xD1-0xD9 = J-R, 0xE2-0xE9 = S-Z
    """
    # EBCDIC-to-ASCII mapping (partial, for letters and digits)
    ebcdic_map = {
        0x40: ord(" "),  # Space
        0xC1: ord("A"),
        0xC2: ord("B"),
        0xC3: ord("C"),
        0xC4: ord("D"),
        0xC5: ord("E"),
        0xC6: ord("F"),
        0xC7: ord("G"),
        0xC8: ord("H"),
        0xC9: ord("I"),
        0xD1: ord("J"),
        0xD2: ord("K"),
        0xD3: ord("L"),
        0xD4: ord("M"),
        0xD5: ord("N"),
        0xD6: ord("O"),
        0xD7: ord("P"),
        0xD8: ord("Q"),
        0xD9: ord("R"),
        0xE2: ord("S"),
        0xE3: ord("T"),
        0xE4: ord("U"),
        0xE5: ord("V"),
        0xE6: ord("W"),
        0xE7: ord("X"),
        0xE8: ord("Y"),
        0xE9: ord("Z"),
        # Digits in EBCDIC (zoned decimal)
        0xF0: ord("0"),
        0xF1: ord("1"),
        0xF2: ord("2"),
        0xF3: ord("3"),
        0xF4: ord("4"),
        0xF5: ord("5"),
        0xF6: ord("6"),
        0xF7: ord("7"),
        0xF8: ord("8"),
        0xF9: ord("9"),
    }
    result = ""
    for i in range(length):
        byte = region[offset + i]
        if byte in ebcdic_map:
            result += chr(ebcdic_map[byte])
        else:
            result += f"\\x{byte:02x}"
    return result


# ---------------------------------------------------------------------------
# REDEFINES Complex Scenario Tests
# ---------------------------------------------------------------------------


class TestRedefinesWriteOriginalReadAlias:
    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.MOVE)
    def test_write_via_original_read_via_alias(self):
        """Write via original field, read via REDEFINES alias.

        WS-ORIGINAL (PIC X(4)) is the base field.
        WS-ALIAS REDEFINES WS-ORIGINAL (also PIC X(4)).
        After MOVE "ABCD" TO WS-ORIGINAL:
        - WS-ALIAS should see the same bytes "ABCD"
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF-ALIAS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-ORIGINAL PIC X(4).",
                "01 WS-ALIAS REDEFINES WS-ORIGINAL PIC X(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 'ABCD' TO WS-ORIGINAL.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        layout = vm.data_layout

        # Both fields should be at the same offset (one redefines the other)
        original_offset = layout["WS-ORIGINAL"]["offset"]
        alias_offset = layout["WS-ALIAS"]["offset"]
        assert original_offset == alias_offset, "REDEFINES should be at same offset"

        # Read via alias and verify we see "ABCD"
        value = _ebcdic_to_ascii(region, alias_offset, 4)
        assert value == "ABCD", f"Alias should see ABCD, got {value}"


class TestRedefinesMultipleAliases:
    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.MOVE)
    def test_multiple_redefines_of_same_field(self):
        """Multiple REDEFINES of the same base field.

        WS-BASE (PIC X(4)) is the base.
        WS-ALIAS1 REDEFINES WS-BASE (PIC X(4)).
        WS-ALIAS2 REDEFINES WS-BASE (PIC X(4)).
        After MOVE "TEST" TO WS-BASE:
        - Both WS-ALIAS1 and WS-ALIAS2 should see "TEST"
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF-MULTI.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-BASE PIC X(4).",
                "01 WS-ALIAS1 REDEFINES WS-BASE PIC X(4).",
                "01 WS-ALIAS2 REDEFINES WS-BASE PIC X(4).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 'TEST' TO WS-BASE.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        layout = vm.data_layout

        base_offset = layout["WS-BASE"]["offset"]
        alias1_offset = layout["WS-ALIAS1"]["offset"]
        alias2_offset = layout["WS-ALIAS2"]["offset"]

        # All three should be at the same offset
        assert base_offset == alias1_offset, "ALIAS1 should redefine BASE"
        assert base_offset == alias2_offset, "ALIAS2 should redefine BASE"

        # Read via both aliases
        value1 = _ebcdic_to_ascii(region, alias1_offset, 4)
        value2 = _ebcdic_to_ascii(region, alias2_offset, 4)
        assert value1 == "TEST", f"ALIAS1 should see TEST, got {value1}"
        assert value2 == "TEST", f"ALIAS2 should see TEST, got {value2}"


class TestRedefinesWriteAliasReadOriginal:
    @covers(CobolFeature.REDEFINES_CLAUSE, CobolFeature.MOVE)
    def test_write_via_alias_read_via_original(self):
        """Write via REDEFINES alias, read via original field.

        WS-ORIGINAL (PIC X(3)) is the base field.
        WS-ALIAS REDEFINES WS-ORIGINAL (also PIC X(3)).
        After MOVE "XYZ" TO WS-ALIAS:
        - WS-ORIGINAL should see the same bytes "XYZ"
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF-WRITE-ALIAS.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-ORIGINAL PIC X(3).",
                "01 WS-ALIAS REDEFINES WS-ORIGINAL PIC X(3).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 'XYZ' TO WS-ALIAS.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        layout = vm.data_layout

        original_offset = layout["WS-ORIGINAL"]["offset"]
        alias_offset = layout["WS-ALIAS"]["offset"]
        assert original_offset == alias_offset

        # Read via original and verify we see "XYZ"
        value = _ebcdic_to_ascii(region, original_offset, 3)
        assert value == "XYZ", f"Original should see XYZ, got {value}"


class TestRedefinesNumericOverAlphanumeric:
    @covers(CobolFeature.REDEFINES_CLAUSE)
    def test_numeric_redefines_of_alphanumeric(self):
        """Numeric REDEFINES of an alphanumeric field.

        WS-STR (PIC X(3)) is the base alphanumeric field.
        WS-NUM REDEFINES WS-STR (PIC 9(3)) is numeric.
        After MOVE 123 TO WS-NUM:
        - WS-STR should see the same bytes as numeric value "123" in zoned format
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-REDEF-NUMERIC.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-STR PIC X(3).",
                "01 WS-NUM REDEFINES WS-STR PIC 9(3).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 123 TO WS-NUM.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        layout = vm.data_layout

        str_offset = layout["WS-STR"]["offset"]
        num_offset = layout["WS-NUM"]["offset"]
        assert str_offset == num_offset

        # When numeric 123 is moved to zoned decimal, each digit becomes 0xFX
        # where X is the digit. So 1 = 0xF1, 2 = 0xF2, 3 = 0xF3.
        # Read via string alias and verify bytes match
        value = _ebcdic_to_ascii(region, str_offset, 3)
        assert value == "123", f"Alphanumeric view should see 123, got {value}"
