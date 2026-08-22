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
            ("PP9", ".001", 1, "1"),
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

    @covers(CobolFeature.PIC_CLAUSE, CobolFeature.MOVE)
    def test_negative_scale_value_reads_back_at_full_magnitude(self):
        """NIST NC124A: PP9 (leading P, scale -3) holding stored digit '1'
        denotes the true value .001 — this file's own module docstring
        (line 10) advertises this exact case, but until now nothing tested
        it: every prior test used positive scale (999PP, 9PP) only.

        Mirrors test_scaled_value_reads_back_at_full_magnitude but for
        negative scale. Receives into PIC 9V999 rather than the docstring's
        literal V999 (no leading digit position): V999 alone (integer_digits
        == 0) hits a PRE-EXISTING, unrelated bug in align_decimal/left_adjust
        — confirmed via a plain `MOVE .001 TO WS-OUT` with WS-OUT PIC V999
        and NO P anywhere, which already stores '000' instead of '001' on
        main before any red-dragon-qhtv change. Out of scope for this task;
        9V999 (one leading digit, always 0 here) sidesteps it without
        weakening the negative-scale coverage this test exists to add.
        """
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. PSCALE3.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-SRC PIC PP9.",
                "01 WS-OUT PIC 9V999.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE .001 TO WS-SRC.",
                "    MOVE WS-SRC TO WS-OUT.",
                "    STOP RUN.",
            ],
            max_steps=20000,
        )
        region = _first_region(vm)
        assert _decode_chars(region, 0, 1) == "1"  # WS-SRC: stored digit unchanged
        assert _decode_chars(region, 1, 4) == "0001"  # WS-OUT: true value .001 restored

    @covers(CobolFeature.PIC_CLAUSE, CobolFeature.MOVE)
    def test_deeply_negative_scale_decode_does_not_corrupt_via_scientific_notation(
        self,
    ):
        """PP9 has scale -3, giving a decode factor of 10**-3 == 0.001, whose
        Python str() is '0.001' — never scientific, so it never exercises the
        trap this test is named for. PPPP9 (4 leading P + 1 digit) has scale
        -5: 1 * 10**-5 == 1e-05, and str(1e-05) == '1e-05' (Python's own
        threshold for switching a float to scientific notation is 1e-4).

        Before the fix, that scientific string reached COBOL_PREPARE_DIGITS
        for the WS-OUT target (whose own scale is 0, since it has no P) and
        corrupted downstream digit extraction: '1e-05' has no '.', so the
        no-decimal-digits branch took the WHOLE string as the integer part
        and zero-padded it, producing '0010005' (treating the 'e' and '-' as
        non-digit-therefore-0 characters at their string positions) instead
        of the correct truncation to 0 (a magnitude of 0.00001 has no
        integer part). This is a second, independently-reachable instance of
        the scientific-notation trap Task 2 fixed on the Decimal-division
        side, found empirically while chasing red-dragon-qhtv's Important-1
        review finding — not on the theory it MIGHT happen, but by
        reproducing '0010005' against the pre-fix code first.
        """
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. PSCALE4.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-SRC PIC PPPP9.",
                "01 WS-OUT PIC 9(7).",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE .00001 TO WS-SRC.",
                "    MOVE WS-SRC TO WS-OUT.",
                "    STOP RUN.",
            ],
            max_steps=20000,
        )
        region = _first_region(vm)
        assert _decode_chars(region, 0, 1) == "1"  # WS-SRC: stored digit unchanged
        # WS-OUT: true value .00001 has no integer part for a 7-digit,
        # zero-decimal-place target -> truncates to 0, not '0010005'.
        assert _decode_chars(region, 1, 7) == "0000000"
