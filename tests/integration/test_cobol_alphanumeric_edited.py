"""Integration tests: MOVE into an alphanumeric-edited receiving item applies
the insertion picture through the full pipeline (source → bridge → IR → CFG → VM).

Asserts the edited character bytes land in the receiving field's memory, which
also pins the field's width: the bridge and the Python descriptor must allocate
the same number of bytes or every later field in the record slides
(red-dragon-ilb6). The pure formatter is unit-tested in
tests/unit/cobol/test_alphanumeric_edited.py.
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
            "PROGRAM-ID. ANEDIT.",
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


@covers(CobolFeature.ALPHANUMERIC_EDITED, CobolFeature.MOVE)
def test_blank_insertion_from_literal():
    vm = _run_edit("XXBXXBXX", "'ABCDEF'")
    assert _decode_chars(_first_region(vm), 0, 8) == "AB CD EF"


@covers(CobolFeature.ALPHANUMERIC_EDITED, CobolFeature.MOVE)
def test_slash_insertion_from_literal():
    vm = _run_edit("XX/XX/XXXX", "'12311994'")
    assert _decode_chars(_first_region(vm), 0, 10) == "12/31/1994"


@covers(CobolFeature.ALPHANUMERIC_EDITED, CobolFeature.MOVE)
def test_zero_insertion_from_literal():
    vm = _run_edit("XXBX0X", "'1234'")
    assert _decode_chars(_first_region(vm), 0, 6) == "12 304"


@covers(CobolFeature.ALPHANUMERIC_EDITED, CobolFeature.MOVE)
def test_short_sender_is_space_filled():
    vm = _run_edit("XXBXX", "'A'")
    assert _decode_chars(_first_region(vm), 0, 5) == "A    "


@covers(CobolFeature.ALPHANUMERIC_EDITED, CobolFeature.MOVE)
def test_field_to_field_move_applies_the_picture():
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. ANEDIT2.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-SRC PIC X(6) VALUE 'ABCDEF'.",
            "01 WS-EDIT PIC XXBXXBXX.",
            "01 WS-AFTER PIC X(3) VALUE 'END'.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    MOVE WS-SRC TO WS-EDIT.",
            "    STOP RUN.",
        ],
        max_steps=20000,
    )
    region = _first_region(vm)
    assert _decode_chars(region, 6, 8) == "AB CD EF"
    # The following field is still where the layout put it — the edited item is
    # eight bytes wide, not six.
    assert _decode_chars(region, 14, 3) == "END"
