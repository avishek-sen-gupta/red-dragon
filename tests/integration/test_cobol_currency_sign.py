"""Integration: SPECIAL-NAMES CURRENCY SIGN IS through the full pipeline.

source -> ProLeap bridge -> JSON special_names -> CobolField -> parse_pic ->
edit_picture -> IR -> CFG -> VM. Every layer has to carry the symbol; a break
anywhere shows up as the field failing to parse or formatting with '$'.

Expected values follow NIST-85 NC107A.CBL, which declares CURRENCY SIGN IS "W"
and asserts PIC WWWWW holding 12 equals '  W12' (red-dragon-3o5f).
"""

import pytest

from cobol_asg.edit_picture import UnsupportedEditPictureError
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


def _run_currency(pic: str, move_src: str, sign: str = "W", clause: bool = True):
    """A record with the edited field between PIC X(4) sentinels.

    Sentinels rather than a standalone field, so a width error is caught too:
    substituting the currency symbol must NOT move any offset
    (see red-dragon-ilb6 and the r9s9 postmortem).
    """
    special = (
        [
            "ENVIRONMENT DIVISION.",
            "CONFIGURATION SECTION.",
            "SPECIAL-NAMES.",
            f'    CURRENCY SIGN IS "{sign}".',
        ]
        if clause
        else []
    )
    return run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. CURTEST.",
            *special,
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


class TestCurrencySignEndToEnd:
    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_configured_symbol_floats_like_a_dollar(self):
        vm = _run_currency("WW,WWW.99", "1234.5")
        region = _first_region(vm)
        assert _decode_chars(region, 0, 4) == "AAAA"
        assert _decode_chars(region, 4, 9) == "W1,234.50"
        assert _decode_chars(region, 13, 4) == "ZZZZ"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_configured_symbol_slides_for_a_small_value(self):
        vm = _run_currency("WW,WWW.99", "7.25")
        region = _first_region(vm)
        assert _decode_chars(region, 4, 9) == "    W7.25"
        assert _decode_chars(region, 13, 4) == "ZZZZ"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_nist_wwwww_case(self):
        """NIST NC107A: PIC WWWWW holding 12 is '  W12'."""
        vm = _run_currency("WWWWW", "12")
        assert _decode_chars(_first_region(vm), 4, 5) == "  W12"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_dollar_still_works_without_the_clause(self):
        """No SPECIAL-NAMES: '$' remains the currency symbol."""
        vm = _run_currency("$$,$$$.99", "1234.5", clause=False)
        region = _first_region(vm)
        assert _decode_chars(region, 4, 9) == "$1,234.50"
        assert _decode_chars(region, 13, 4) == "ZZZZ"

    @covers(CobolFeature.NUMERIC_EDITED, CobolFeature.MOVE)
    def test_dollar_is_inert_when_another_symbol_is_configured(self):
        """With CURRENCY SIGN IS 'W', '$' is an ordinary character. It must not
        also behave as currency, or the picture would have two of them."""
        vm = _run_currency("WW,WWW.99", "1234.5", sign="W")
        assert "$" not in _decode_chars(_first_region(vm), 4, 9)

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_multi_character_currency_is_refused(self):
        with pytest.raises(UnsupportedEditPictureError, match="CURRENCY"):
            _run_currency("WW,WWW.99", "1234.5", sign="EUR")
