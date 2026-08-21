"""Integration tests: MOVE into a numeric-edited receiving item applies the
edit picture through the full pipeline (source → bridge → IR → CFG → VM).

Exercises COBOL numeric editing (sign / Z suppression / comma / decimal) end to
end, asserting the formatted character bytes land in the receiving field's
memory. The pure formatter is unit-tested in tests/unit/cobol/test_edit_picture.

Most cases use a *literal* source so they exercise edit formatting with full
fractional fidelity. Field→field MOVE of a fractional numeric-DISPLAY source
currently loses its fraction in the VM decode→string path (a pre-existing bug
independent of edit pictures — see red-dragon issue for numeric MOVE fraction
loss); the field-source case below therefore uses a whole-number value.
"""

import pytest

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
    """Enforce the required PROLEAP_BRIDGE_JAR for run()/compile_directory-based
    tests (fails loudly via bridge_jar if it's unset)."""


def _decode_chars(region, offset: int, length: int) -> str:
    """Decode EBCDIC bytes (cp037) to an ASCII string for assertion."""
    return bytes(region[offset : offset + length]).decode("cp037")


def _run_edit(pic: str, move_src: str):
    """Run a one-field program that MOVEs move_src into a PIC-edited field."""
    return run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. EDITT.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            f"77 WS-EDIT PIC {pic}.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            f"    MOVE {move_src} TO WS-EDIT.",
            "    STOP RUN.",
        ],
        max_steps=20000,
    )


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
def test_fixed_sign_positive():
    vm = _run_edit("+99999999.99", "12345.67")
    assert _decode_chars(_first_region(vm), 0, 12) == "+00012345.67"


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
def test_fixed_sign_negative():
    vm = _run_edit("+99999999.99", "-12345.67")
    assert _decode_chars(_first_region(vm), 0, 12) == "-00012345.67"


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
def test_fixed_sign_zero():
    vm = _run_edit("+99999999.99", "0")
    assert _decode_chars(_first_region(vm), 0, 12) == "+00000000.00"


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
def test_suppression_with_commas():
    vm = _run_edit("+ZZZ,ZZZ,ZZZ.99", "1234.56")
    assert _decode_chars(_first_region(vm), 0, 15) == "+      1,234.56"


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
def test_suppression_zero_keeps_fraction():
    vm = _run_edit("+ZZZ,ZZZ,ZZZ.99", "0")
    assert _decode_chars(_first_region(vm), 0, 15) == "+           .00"


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
def test_trailing_sign_negative():
    vm = _run_edit("Z(9).99-", "-123.45")
    assert _decode_chars(_first_region(vm), 0, 13) == "      123.45-"


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
def test_all_suppressible_zero_blanks_field():
    vm = _run_edit("-ZZZ,ZZZ,ZZZ.ZZ", "0")
    assert _decode_chars(_first_region(vm), 0, 15) == " " * 15


@covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
def test_field_source_whole_number():
    """Field→field MOVE into an edited item: a numeric-DISPLAY source moves and
    formats. Uses a whole number to avoid the unrelated field-decode fraction
    loss; the integer digits and edit mask are what this asserts."""
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. EDITF.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "77 WS-SRC  PIC 9(9) VALUE 42.",
            "77 WS-EDIT PIC +99999999.99.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    MOVE WS-SRC TO WS-EDIT.",
            "    STOP RUN.",
        ],
        max_steps=20000,
    )
    region = _first_region(vm)
    # WS-SRC is 9 bytes; WS-EDIT starts at offset 9.
    assert _decode_chars(region, 9, 12) == "+00000042.00"


class TestFloatingAndCheckProtectionEndToEnd:
    """Floating currency/sign, '*' check protection and CR/DB through the full
    source -> bridge -> IR -> CFG -> VM pipeline (red-dragon-5f4g).

    Replaces TestUnsupportedEditPicturesAreRejected, whose premise (that these
    pictures abort at ingestion) was red-dragon-0599's holding position while
    they were unimplemented.

    These also prove the bridge and the Python formatter agree on the field
    WIDTH: the assertion decodes exactly byte_length bytes, so a disagreement
    between the bridge's allocation and Python's read would corrupt the
    expected string (red-dragon-ilb6).
    """

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_floating_currency_slides_with_the_value(self):
        vm = _run_edit("$$,$$$.99", "1234.5")
        assert _decode_chars(_first_region(vm), 0, 9) == "$1,234.50"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_floating_currency_hugs_a_small_value(self):
        """The '$' moves right as the value shrinks — the whole point of a
        floating insertion, and the case a fixed '$' cannot express."""
        vm = _run_edit("$$,$$$.99", "7.25")
        assert _decode_chars(_first_region(vm), 0, 9) == "    $7.25"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_all_floating_picture_runs(self):
        """PIC $$$$.$$ used to abort the whole program at ingestion."""
        vm = _run_edit("$$$$.$$", "12.34")
        assert _decode_chars(_first_region(vm), 0, 7) == " $12.34"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_check_protection_fills_with_asterisks(self):
        vm = _run_edit("**,***.99", "12.3")
        assert _decode_chars(_first_region(vm), 0, 9) == "****12.30"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_trailing_cr_absent_on_a_positive_value(self):
        """The bug that motivated the whole thread: CR was stamped on positive
        balances, reporting a credit on a debit."""
        vm = _run_edit("ZZZ.99CR", "4.5")
        assert _decode_chars(_first_region(vm), 0, 8) == "  4.50  "

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_trailing_cr_present_on_a_negative_value(self):
        vm = _run_edit("ZZZ.99CR", "-4.5")
        assert _decode_chars(_first_region(vm), 0, 8) == "  4.50CR"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_single_fixed_currency_still_runs(self):
        vm = _run_edit("$ZZZ,ZZZ.99", "1234.5")
        assert _decode_chars(_first_region(vm), 0, 11) == "$  1,234.50"


def _run_record(pic: str, move_src: str):
    """Run a program where the edited field sits BETWEEN two sentinel fields.

    The sentinels are what make this different from _run_edit: if the edited
    field's width is wrong, it overruns or under-fills and the sentinel bytes
    move. A single standalone 77-level field cannot detect that.
    """
    return run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. EDITREC.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-REC.",
            "   05 WS-BEFORE PIC X(4) VALUE 'AAAA'.",
            f"   05 WS-AMT PIC {pic}.",
            "   05 WS-AFTER PIC X(4) VALUE 'ZZZZ'.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            f"    MOVE {move_src} TO WS-AMT.",
            "    STOP RUN.",
        ],
        max_steps=20000,
    )


class TestEditedFieldInARecordLayout:
    """Edited pictures inside a real record, flanked by sentinel fields.

    Everything else in this module exercises a single standalone 77-level
    field, which cannot detect a WIDTH error: with nothing after it, an
    over-wide or under-wide field has no neighbour to corrupt.

    That is precisely the bug class this whole area kept producing —
    red-dragon-ilb6 shipped a picture allocated ZERO bytes whose successor was
    laid on top of it, and red-dragon-r9s9 shipped three pictures where Python
    read two bytes further than the bridge allocated. Both were invisible to
    width-in-isolation assertions.

    Asserting the sentinels land exactly where they should is the assertion
    that catches it: the bridge computes the offsets, Python computes the read
    length, and these tests fail if the two disagree.
    """

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_floating_currency_does_not_disturb_neighbours(self):
        vm = _run_record("$$,$$$.99", "1234.5")
        region = _first_region(vm)
        assert _decode_chars(region, 0, 4) == "AAAA"
        assert _decode_chars(region, 4, 9) == "$1,234.50"
        assert _decode_chars(region, 13, 4) == "ZZZZ"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_floating_currency_short_value_does_not_disturb_neighbours(self):
        """The '$' slides right for a small value, but the FIELD does not
        shrink — the sentinel must stay at offset 13."""
        vm = _run_record("$$,$$$.99", "7.25")
        region = _first_region(vm)
        assert _decode_chars(region, 0, 4) == "AAAA"
        assert _decode_chars(region, 4, 9) == "    $7.25"
        assert _decode_chars(region, 13, 4) == "ZZZZ"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_all_floating_picture_occupies_its_full_width(self):
        """PIC $$$$.$$ is the picture the bridge used to allocate ZERO bytes
        for, laying the next field directly on top of it (red-dragon-ilb6).
        The sentinel at offset 11 is the assertion that would have caught it."""
        vm = _run_record("$$$$.$$", "12.34")
        region = _first_region(vm)
        assert _decode_chars(region, 0, 4) == "AAAA"
        assert _decode_chars(region, 4, 7) == " $12.34"
        assert _decode_chars(region, 11, 4) == "ZZZZ"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_check_protection_does_not_disturb_neighbours(self):
        vm = _run_record("**,***.99", "12.3")
        region = _first_region(vm)
        assert _decode_chars(region, 0, 4) == "AAAA"
        assert _decode_chars(region, 4, 9) == "****12.30"
        assert _decode_chars(region, 13, 4) == "ZZZZ"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_trailing_cr_occupies_two_bytes_on_a_positive_value(self):
        """CR emits two SPACES when non-negative — it must still occupy its
        two bytes, or the sentinel slides left."""
        vm = _run_record("ZZZ.99CR", "4.5")
        region = _first_region(vm)
        assert _decode_chars(region, 0, 4) == "AAAA"
        assert _decode_chars(region, 4, 8) == "  4.50  "
        assert _decode_chars(region, 12, 4) == "ZZZZ"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_blank_insertion_field_does_not_disturb_neighbours(self):
        """PIC 9(5)BB9 is one of the three pictures where Python read 8 bytes
        from a 6-byte bridge allocation until red-dragon-ilb6."""
        vm = _run_record("9(5)BB9", "123456")
        region = _first_region(vm)
        assert _decode_chars(region, 0, 4) == "AAAA"
        assert _decode_chars(region, 4, 8) == "12345  6"
        assert _decode_chars(region, 12, 4) == "ZZZZ"
