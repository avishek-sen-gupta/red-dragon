"""End-to-end: IF item IS [NOT] class-name tests the item against the CLASS clause."""

from __future__ import annotations

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.io_provider import StubIOProvider
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    to_fixed,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


def _flag(condition: str, flag: str) -> list[str]:
    return [f"    IF {condition}", f'        MOVE "Y" TO {flag}', "    END-IF."]


@covers(CobolFeature.CLASS_NAME)
def test_class_name_conditions_test_every_character(
    capsys: pytest.CaptureFixture[str],
) -> None:
    flags = [f"F{n}" for n in range(1, 7)]
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. CLASSES.",
            "ENVIRONMENT DIVISION.",
            "CONFIGURATION SECTION.",
            "SPECIAL-NAMES.",
            '    CLASS A-THRU-D IS "A" THRU "D"',
            "    CLASS ORDINAL-A-D IS 197 THROUGH 194",
            '    CLASS JUST-ABCD "ABCD".',
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            '01 ADCBA PIC X(5) VALUE "ADCBA".',
            '01 VWXYZ PIC X(5) VALUE "VWXYZ".',
            *(f'01 {flag} PIC X VALUE "N".' for flag in flags),
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *_flag("ADCBA IS A-THRU-D", "F1"),
            *_flag("VWXYZ IS NOT A-THRU-D", "F2"),
            *_flag("ADCBA ORDINAL-A-D", "F3"),
            *_flag("VWXYZ ORDINAL-A-D", "F4"),
            *_flag("ADCBA IS NOT JUST-ABCD", "F5"),
            *_flag("ADCBA JUST-ABCD AND VWXYZ NOT JUST-ABCD", "F6"),
            f"    DISPLAY {' '.join(flags)}.",
            "    STOP RUN.",
        ]
    )
    run(source=source, language="cobol", max_steps=5000, io_provider=StubIOProvider())
    assert capsys.readouterr().out == "YYYNNY"
