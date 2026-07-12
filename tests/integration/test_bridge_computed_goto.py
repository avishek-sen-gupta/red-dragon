"""The ProLeap bridge serializes GO TO ... DEPENDING ON structurally."""

from __future__ import annotations

from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    to_fixed,
)


def _raw(source_lines: list[str], bridge_jar: str) -> str:
    """Parse COBOL source and return the raw ASG JSON string."""
    fixed = to_fixed(source_lines)
    return RealSubprocessRunner().run(["java", "-jar", bridge_jar], fixed)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_emits_computed_goto_shape(bridge_jar):
    src = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. CGOTO.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-IDX PIC 9 VALUE 1.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        "    GO TO P1 P2 P3 DEPENDING ON WS-IDX.",
        "    STOP RUN.",
        "P1.",
        "    STOP RUN.",
        "P2.",
        "    STOP RUN.",
        "P3.",
        "    STOP RUN.",
    ]
    raw = _raw(src, bridge_jar)
    assert '"form": "computed"' in raw or '"form":"computed"' in raw
    assert '"index"' in raw
    assert "P1" in raw and "P2" in raw and "P3" in raw
