"""Integration: PIC P decimal scaling through the full pipeline.

Asserts STORED BYTES, never round trips. A round trip applies the same scale
in both directions and passes against the broken pre-fix code, so it proves
nothing (red-dragon-qhtv).

Expected values follow NIST-85 NC124A.CBL:
    01 WORK-AREA-27 PICTURE S9PP  VALUE 200    -> moved to X(3)   = "200"
    01 WORK-AREA-30 PICTURE 999PP VALUE 00900  -> moved to ZZZPP  = "  9"
    01 WORK-AREA-32 PICTURE PP9   VALUE .001   -> moved to V999   = .001
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
    """Enforce PROLEAP_BRIDGE_JAR for run()-based tests."""


def _decode_chars(region, offset: int, length: int) -> str:
    return bytes(region[offset : offset + length]).decode("cp037")


def _run_scaled(pic: str, move_src: str):
    """A P-scaled field between PIC X(4) sentinels.

    Sentinels catch a width error at the same time: P occupies no storage, so
    the field must be exactly its digit count wide and the sentinels must not
    move (red-dragon-ilb6).
    """
    return run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. PSCALE.",
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


class TestScaledFieldStoresSignificantDigits:
    @covers(CobolFeature.PIC_CLAUSE, CobolFeature.MOVE)
    @pytest.mark.parametrize(
        ("pic", "value", "width", "stored"),
        [
            ("999PP", "900", 3, "009"),
            ("999PP", "12300", 3, "123"),
            ("9PP", "200", 1, "2"),
        ],
    )
    def test_stored_bytes(self, pic: str, value: str, width: int, stored: str):
        region = _first_region(_run_scaled(pic, value))
        assert _decode_chars(region, 0, 4) == "AAAA"
        assert _decode_chars(region, 4, width) == stored
        assert _decode_chars(region, 4 + width, 4) == "ZZZZ"

    @covers(CobolFeature.PIC_CLAUSE, CobolFeature.MOVE)
    def test_scaled_value_reads_back_at_full_magnitude(self):
        """999PP holding stored digits '009' (scale +2) denotes the true value
        900 — reading it (via a field-to-field MOVE, which exercises DECODE,
        unlike a literal MOVE) and writing it into a wide, non-edited receiver
        must show the full magnitude 00900, not the raw stored digits 00009.

        NOTE: the NIST NC124A source for this case moves 999PP into an EDITED
        picture (ZZZPP), expecting '  9' (Z-suppressed, P never displayed).
        That case is intentionally NOT used here: interpreter/cobol/edit_picture.py
        does not yet apply P scaling to numeric-edited targets (see its module
        docstring, "Still NOT supported: P scaling semantics") — that is Task 4's
        job. A ZZZPP target here would silently assert today's un-scaled (wrong)
        edited output as if it were correct, hiding that gap. This test instead
        uses a plain PIC 9(5) receiver to isolate and prove DECODE's magnitude
        restoration without depending on Task 4.
        """
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. PSCALE2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-SRC PIC 999PP.",
                "01 WS-OUT PIC 9(5).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 00900 TO WS-SRC.",
                "    MOVE WS-SRC TO WS-OUT.",
                "    STOP RUN.",
            ],
            max_steps=20000,
        )
        region = _first_region(vm)
        assert _decode_chars(region, 0, 3) == "009"  # WS-SRC: stored digits unchanged
        assert _decode_chars(region, 3, 5) == "00900"  # WS-OUT: full magnitude restored
