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

import os

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    JAR_PATH,
    JAR_AVAILABLE,
    first_region as _first_region,
    run_cobol,
)

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


@pytest.fixture(autouse=True, scope="session")
def _set_bridge_jar_env():
    old = os.environ.get("PROLEAP_BRIDGE_JAR")
    os.environ["PROLEAP_BRIDGE_JAR"] = JAR_PATH
    yield
    if old is None:
        os.environ.pop("PROLEAP_BRIDGE_JAR", None)
    else:
        os.environ["PROLEAP_BRIDGE_JAR"] = old


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
