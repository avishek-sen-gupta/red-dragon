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

from interpreter.cobol.edit_picture import UnsupportedEditPictureError
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


class TestUnsupportedEditPicturesAreRejected:
    """A program declaring an edit picture RedDragon cannot honour fails to
    LOAD, rather than running and producing well-formed wrong output
    (red-dragon-0599). Real support for these symbols is red-dragon-5f4g.

    These go through the full source → bridge → field-ingestion path, so they
    also prove the ProLeap bridge hands the raw picture through unchanged —
    the Java side sizes these pictures happily and only the Python gate stops
    them.
    """

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_floating_currency_field_aborts_the_program(self):
        with pytest.raises(UnsupportedEditPictureError, match="floating"):
            _run_edit("$$,$$$.99", "1234.5")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_all_floating_currency_field_aborts_the_program(self):
        with pytest.raises(UnsupportedEditPictureError, match="floating"):
            _run_edit("$$$$.$$", "12.34")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_check_protection_field_aborts_the_program(self):
        with pytest.raises(UnsupportedEditPictureError, match=r"check protection"):
            _run_edit("**,***.99", "12.3")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_trailing_cr_field_aborts_the_program(self):
        with pytest.raises(UnsupportedEditPictureError, match="CR"):
            _run_edit("ZZZ.99CR", "4.5")

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_abort_message_names_the_declared_field(self):
        """The whole point of failing at load is a message the user can act
        on — it must identify the field, not just the picture."""
        with pytest.raises(UnsupportedEditPictureError, match="WS-EDIT"):
            _run_edit("$$,$$$.99", "1234.5")

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_single_fixed_currency_field_still_runs(self):
        """PIC $ZZZ,ZZZ.99 formats correctly today and must keep running —
        the rejection distinguishes a run of one from a floating run."""
        vm = _run_edit("$ZZZ,ZZZ.99", "1234.5")
        assert _decode_chars(_first_region(vm), 0, 11) == "$  1,234.50"
