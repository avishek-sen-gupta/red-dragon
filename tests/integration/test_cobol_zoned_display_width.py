"""A numeric USAGE DISPLAY item is a fixed-width field of exactly PICTURE-many bytes.

``PIC 9(09) VALUE 020973888`` occupies nine zoned bytes and every context that
consumes the item as CHARACTERS — DISPLAY, reference modification, a STRING
sending operand — must see those nine digit characters. Reading it as a number
and formatting the number back drops the leading zero, and a subsequent
reference modification then slices at offsets that have all slid left: the
CardDemo SSN renders 209-73-888 instead of 020-97-3888 (red-dragon-wlms).

Storage was never the defect — the region already holds the nine zoned bytes —
so these tests pin both halves: the stored bytes AND what each character-consuming
context reads back out of them.
"""

import pytest

from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
)
from tests.integration.cobol_helpers import (
    first_region as _first_region,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR for this test module."""


def _chars(region, offset: int, length: int) -> str:
    return EbcdicTable.ebcdic_to_ascii(bytes(region[offset : offset + length])).decode(
        "ascii"
    )


_WS = [
    "01 ALPHA-IN     PIC X(09) VALUE '020973888'.",
    "01 A-VALUE      PIC 9(09) VALUE 020973888.",
    "01 B-MOVED      PIC 9(09).",
    "01 C-FROMALPHA  PIC 9(09).",
    "01 D-REC.",
    "   05 D-SSN     PIC 9(09).",
]
_POPULATE = [
    "    MOVE 20973888 TO B-MOVED",
    "    MOVE ALPHA-IN TO C-FROMALPHA",
    "    MOVE ALPHA-IN TO D-REC",
]

A_VALUE_AT = 9
B_MOVED_AT = 18
C_FROMALPHA_AT = 27
D_SSN_AT = 36
RECEIVER_AT = 45


def _program(extra_ws: list[str], body: list[str]) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. ZWIDTH.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        *_WS,
        *extra_ws,
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        *_POPULATE,
        *body,
        "    STOP RUN.",
    ]


class TestZonedDisplayWidth:
    @covers(CobolFeature.VALUE_CLAUSE, CobolFeature.MOVE)
    def test_all_four_population_paths_store_nine_zoned_bytes(self):
        """VALUE, MOVE literal, MOVE alphanumeric and a group MOVE each fill all
        nine bytes — the field IS nine bytes wide, not merely printed so."""
        vm = run_cobol(_program([], []), max_steps=5000)
        region = _first_region(vm)
        for name, offset in (
            ("A-VALUE", A_VALUE_AT),
            ("B-MOVED", B_MOVED_AT),
            ("C-FROMALPHA", C_FROMALPHA_AT),
            ("D-SSN", D_SSN_AT),
        ):
            assert _chars(region, offset, 9) == "020973888", name

    @covers(CobolFeature.DISPLAY, CobolFeature.VALUE_CLAUSE)
    def test_display_renders_the_full_picture_width(self, capsys):
        """DISPLAY of a numeric-DISPLAY item shows its zoned characters, so a
        PIC 9(09) always prints nine of them.

        The surrounding quoted literals keep their quotes in DISPLAY output, which
        is a separate matter; only the field's own nine characters are asserted.
        """
        run_cobol(
            _program(
                [],
                [
                    "    DISPLAY 'A=[' A-VALUE ']'",
                    "    DISPLAY 'B=[' B-MOVED ']'",
                    "    DISPLAY 'C=[' C-FROMALPHA ']'",
                    "    DISPLAY 'D=[' D-SSN ']'",
                ],
            ),
            max_steps=5000,
        )
        out = capsys.readouterr().out
        assert out.count("020973888") == 4, out

    @covers(CobolFeature.MOVE, CobolFeature.USAGE_DISPLAY)
    def test_ref_mod_addresses_the_zoned_bytes(self):
        """A ref-mod slice of a numeric-DISPLAY item reads the stored bytes at the
        stated offsets, so (1:3) of 020973888 is 020 — asserted on the receiving
        fields' record image, not on printed output."""
        vm = run_cobol(
            _program(
                [
                    "01 OUT-HEAD PIC X(03).",
                    "01 OUT-MID  PIC X(02).",
                    "01 OUT-TAIL PIC X(04).",
                ],
                [
                    "    MOVE D-SSN(1:3) TO OUT-HEAD",
                    "    MOVE D-SSN(4:2) TO OUT-MID",
                    "    MOVE D-SSN(6:4) TO OUT-TAIL",
                ],
            ),
            max_steps=5000,
        )
        region = _first_region(vm)
        assert _chars(region, RECEIVER_AT, 3) == "020"
        assert _chars(region, RECEIVER_AT + 3, 2) == "97"
        assert _chars(region, RECEIVER_AT + 5, 4) == "3888"

    @covers(CobolFeature.STRING_VERB, CobolFeature.STRING_REF_MOD)
    def test_string_of_ref_mod_slices_builds_the_ssn(self):
        """The CardDemo shape: STRING over three ref-mod slices of a PIC 9(09)."""
        vm = run_cobol(
            _program(
                ["01 OUT-SSN PIC X(11)."],
                [
                    "    STRING D-SSN(1:3) '-' D-SSN(4:2) '-' D-SSN(6:4)",
                    "        DELIMITED BY SIZE INTO OUT-SSN",
                ],
            ),
            max_steps=5000,
        )
        region = _first_region(vm)
        assert _chars(region, RECEIVER_AT, 11) == "020-97-3888"

    @covers(CobolFeature.STRING_VERB)
    def test_string_of_whole_field_sends_its_characters(self):
        """A whole numeric-DISPLAY sending operand contributes all nine characters."""
        vm = run_cobol(
            _program(
                ["01 OUT-SSN PIC X(11)."],
                ["    STRING D-SSN DELIMITED BY SIZE INTO OUT-SSN"],
            ),
            max_steps=5000,
        )
        region = _first_region(vm)
        assert _chars(region, RECEIVER_AT, 9) == "020973888"

    @covers(CobolFeature.IF_ELSE, CobolFeature.USAGE_DISPLAY)
    def test_ref_mod_in_a_condition_compares_the_zoned_bytes(self):
        """A ref-mod slice used as a condition operand sees the same characters.

        The second IF is the guard that keeps the first honest: decoding the field
        to a number made every ref-mod comparison against a literal true, so an
        assertion on the matching literal alone passed for the wrong reason.
        """
        vm = run_cobol(
            _program(
                ["01 OUT-FLAG PIC X(01) VALUE 'N'."],
                [
                    "    IF D-SSN(1:3) = '020'",
                    "        MOVE 'Y' TO OUT-FLAG",
                    "    END-IF",
                    "    IF D-SSN(1:3) = '209'",
                    "        MOVE 'X' TO OUT-FLAG",
                    "    END-IF",
                ],
            ),
            max_steps=5000,
        )
        region = _first_region(vm)
        assert _chars(region, RECEIVER_AT, 1) == "Y"
