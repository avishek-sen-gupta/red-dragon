"""Integration tests for COBOL MOVE CORRESPONDING.

These tests exercise the full MOVE CORRESPONDING pipeline:
COBOL source → ProLeap bridge → IR → CFG → VM execution.
They verify that only matching field names are copied between group items.

Requires the ProLeap bridge JAR to be available (set PROLEAP_BRIDGE_JAR env var).
Tests skip gracefully when the JAR is absent.
"""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,
    decode_zoned_unsigned as _decode_zoned_unsigned,
    first_region as _first_region,
    run_cobol as _run_cobol,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR for run()/compile_directory-based
    tests (fails loudly via bridge_jar if it's unset)."""


def _ebcdic_to_ascii(region: list[int], offset: int, length: int) -> str:
    """Decode EBCDIC alphanumeric field to ASCII string.

    Maps common EBCDIC characters to ASCII:
    0x40 = space, 0xC1-0xC9 = A-I, 0xD1-0xD9 = J-R, 0xE2-0xE9 = S-Z
    """
    # EBCDIC-to-ASCII mapping (partial, for letters)
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
# MOVE CORRESPONDING Tests
# ---------------------------------------------------------------------------


class TestMoveCorrespondingBasic:
    @covers(
        CobolFeature.MOVE_CORRESPONDING,
        CobolFeature.GROUP_ITEM,
        CobolFeature.PIC_CLAUSE,
    )
    def test_basic_move_corresponding(self):
        """MOVE CORRESPONDING copies matching fields; unmatched fields unchanged.

        SOURCE-REC has MATCHED (5) and SOURCE-ONLY (77).
        TARGET-REC has MATCHED (9) and TARGET-ONLY (88).
        After MOVE CORRESPONDING SOURCE-REC TO TARGET-REC:
        - SOURCE-REC.SOURCE-ONLY should stay 77 (not in target)
        - TARGET-REC.TARGET-ONLY should stay 88 (no match in source)
        - The MATCHED field should have been copied (source value 5 → target)
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MOVCORR.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 SOURCE-REC.",
                "   05 MATCHED PIC 9(3) VALUE 5.",
                "   05 SOURCE-ONLY PIC 9(3) VALUE 77.",
                "01 TARGET-REC.",
                "   05 MATCHED PIC 9(3) VALUE 9.",
                "   05 TARGET-ONLY PIC 9(3) VALUE 88.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE CORRESPONDING SOURCE-REC TO TARGET-REC.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        layout = vm.data_layout

        # Get field offsets from layout
        matched_offset = layout["MATCHED"]["offset"]
        source_only_offset = layout["SOURCE-ONLY"]["offset"]
        target_only_offset = layout["TARGET-ONLY"]["offset"]

        # SOURCE-REC.SOURCE-ONLY should be unchanged: 77
        assert _decode_zoned_unsigned(region, source_only_offset, 3) == 77

        # TARGET-REC.TARGET-ONLY should be unchanged: 88
        assert _decode_zoned_unsigned(region, target_only_offset, 3) == 88

        # The MATCHED field in layout points to TARGET-REC.MATCHED (last one wins in flattening)
        # After MOVE CORRESPONDING, TARGET-REC.MATCHED should be 5 (copied from source)
        assert _decode_zoned_unsigned(region, matched_offset, 3) == 5


class TestMoveCorrespondingMultipleTargets:
    @covers(
        CobolFeature.MOVE_CORRESPONDING,
        CobolFeature.GROUP_ITEM,
        CobolFeature.PIC_CLAUSE,
    )
    def test_move_corresponding_multiple_targets(self):
        """MOVE CORRESPONDING can copy to multiple targets in one statement.

        SOURCE-REC has ITEM (99).
        TARGET1-REC has ITEM (initially 1) and FIELD1 (initially 11).
        TARGET2-REC has ITEM (initially 2) and FIELD2 (initially 22).
        After MOVE CORRESPONDING SOURCE-REC TO TARGET1-REC TARGET2-REC:
        - Both target ITEM fields should be 99
        - FIELD1 should be unchanged: 11
        - FIELD2 should be unchanged: 22
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MOVCORR2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 SOURCE-REC.",
                "   05 ITEM PIC 9(3) VALUE 99.",
                "01 TARGET1-REC.",
                "   05 ITEM PIC 9(3) VALUE 1.",
                "   05 FIELD1 PIC 9(3) VALUE 11.",
                "01 TARGET2-REC.",
                "   05 ITEM PIC 9(3) VALUE 2.",
                "   05 FIELD2 PIC 9(3) VALUE 22.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE CORRESPONDING SOURCE-REC TO TARGET1-REC TARGET2-REC.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        layout = vm.data_layout

        # Get offsets from layout
        item_offset = layout["ITEM"]["offset"]
        field1_offset = layout["FIELD1"]["offset"]
        field2_offset = layout["FIELD2"]["offset"]

        # FIELD1 and FIELD2 should be unchanged
        assert _decode_zoned_unsigned(region, field1_offset, 3) == 11
        assert _decode_zoned_unsigned(region, field2_offset, 3) == 22

        # ITEM (which points to last one, TARGET2-REC) should be 99
        assert _decode_zoned_unsigned(region, item_offset, 3) == 99


class TestMoveCorrespondingNoMatches:
    @covers(
        CobolFeature.MOVE_CORRESPONDING,
        CobolFeature.GROUP_ITEM,
        CobolFeature.PIC_CLAUSE,
    )
    def test_move_corresponding_no_matches(self):
        """MOVE CORRESPONDING is a no-op when no field names match.

        SRC-REC has ALPHA (alphanumeric "TEST").
        TGT-REC has BETA (alphanumeric, initially "XXXX").
        After MOVE CORRESPONDING SRC-REC TO TGT-REC:
        - No fields match, so target should be unchanged
        - SRC-REC.ALPHA should remain "TEST"
        - TGT-REC.BETA should remain "XXXX"
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MOVCORR3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 SRC-REC.",
                "   05 ALPHA PIC X(4) VALUE 'TEST'.",
                "01 TGT-REC.",
                "   05 BETA PIC X(4) VALUE 'XXXX'.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE CORRESPONDING SRC-REC TO TGT-REC.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        layout = vm.data_layout

        # Get offsets from layout
        alpha_offset = layout["ALPHA"]["offset"]
        beta_offset = layout["BETA"]["offset"]

        # Source should remain "TEST"
        assert _ebcdic_to_ascii(region, alpha_offset, 4) == "TEST"

        # Target should remain "XXXX" (no matching field in source)
        assert _ebcdic_to_ascii(region, beta_offset, 4) == "XXXX"


class TestMoveCorrespondingPartialOverlap:
    @covers(
        CobolFeature.MOVE_CORRESPONDING,
        CobolFeature.GROUP_ITEM,
        CobolFeature.PIC_CLAUSE,
    )
    def test_move_corresponding_partial_overlap(self):
        """MOVE CORRESPONDING copies matching fields and leaves unmatched ones unchanged.

        SRC-REC has STATE (numeric 5) and SRC-FILLER (numeric 77).
        TGT-REC has STATE (numeric 9) and TGT-FILLER (numeric 88).
        After MOVE CORRESPONDING SRC-REC TO TGT-REC:
        - STATE matches: target's STATE should become 5
        - SRC-FILLER has no target match: stays 77
        - TGT-FILLER has no source match: stays 88
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-MOVCORR4.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 SRC-REC.",
                "   05 STATE PIC 9(3) VALUE 5.",
                "   05 SRC-FILLER PIC 9(3) VALUE 77.",
                "01 TGT-REC.",
                "   05 STATE PIC 9(3) VALUE 9.",
                "   05 TGT-FILLER PIC 9(3) VALUE 88.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE CORRESPONDING SRC-REC TO TGT-REC.",
                "    STOP RUN.",
            ]
        )
        region = _first_region(vm)
        layout = vm.data_layout

        # Get offsets from layout
        state_offset = layout["STATE"]["offset"]
        src_filler_offset = layout["SRC-FILLER"]["offset"]
        tgt_filler_offset = layout["TGT-FILLER"]["offset"]

        # SRC-FILLER (no target match) should remain 77
        assert _decode_zoned_unsigned(region, src_filler_offset, 3) == 77

        # TGT-FILLER (no source match) should remain 88
        assert _decode_zoned_unsigned(region, tgt_filler_offset, 3) == 88

        # STATE (matches) should be 5
        assert _decode_zoned_unsigned(region, state_offset, 3) == 5
