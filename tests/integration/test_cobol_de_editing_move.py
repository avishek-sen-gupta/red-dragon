"""Integration: MOVE of a numeric-edited item to a numeric item de-edits the sender."""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


@covers(CobolFeature.MOVE, CobolFeature.NUMERIC_EDITED)
def test_move_numeric_edited_to_numeric_recovers_the_signed_value():
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. DEEDIT.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 N-CR    PIC S9(4)V99 SIGN LEADING SEPARATE.",
            "01 N-INS   PIC S99V9(6) SIGN LEADING SEPARATE.",
            "01 N-TRL   PIC S9(4) SIGN LEADING SEPARATE.",
            "01 N-POS   PIC S9(4)V99 SIGN LEADING SEPARATE.",
            "01 N-ED    PIC +9(4).99.",
            "01 E-CR    PIC $(4)9.99CR.",
            "01 E-INS   PIC --9B.99B99/99.",
            "01 E-TRL   PIC Z(4)-.",
            "01 E-POS   PIC $(4)9.99CR.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    MOVE -123.45 TO E-CR",
            "    MOVE -42.9876 TO E-INS",
            "    MOVE -17 TO E-TRL",
            "    MOVE 123.45 TO E-POS",
            "    MOVE E-CR TO N-CR",
            "    MOVE E-INS TO N-INS",
            "    MOVE E-TRL TO N-TRL",
            "    MOVE E-POS TO N-POS",
            "    MOVE E-CR TO N-ED",
            "    STOP RUN.",
        ],
        max_steps=100_000,
    )
    assert bytes(first_region(vm)[:36]).decode("cp037") == (
        "-012345" "-42987600" "-0017" "+012345" "-0123.45"
    )
