from __future__ import annotations

import json

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.covers import covers
from tests.integration.cobol_helpers import JAR_AVAILABLE, JAR_PATH

pytestmark = pytest.mark.skipif(not JAR_AVAILABLE, reason="ProLeap JAR not built")


def _fixed(lines: list[str]) -> str:
    return "\n".join("       " + line for line in lines) + "\n"


def _parse(src: list[str]) -> dict:
    raw = RealSubprocessRunner().run(["java", "-jar", JAR_PATH], _fixed(src))
    return json.loads(raw)


@covers(CobolFeature.OCCURS_FIXED)
def test_bridge_emits_bare_name_and_subscripts():
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-IDX PIC 9(4) COMP.",
            "01 WS-TAB.",
            "   05 WS-ELEM PIC 9(4) OCCURS 5 TIMES.",
            "PROCEDURE DIVISION.",
            "    MOVE WS-ELEM(WS-IDX) TO WS-IDX.",
            "    GOBACK.",
        ]
    )
    move = obj["statements"][0]
    src = move["operands"][0]
    assert src["name"] == "WS-ELEM"  # bare base, no "(WS-IDX)"
    assert src["subscripts"] == ["WS-IDX"]  # structured


@covers(CobolFeature.OCCURS_FIXED)
def test_bridge_keeps_all_subscripts_2d():
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 I PIC 9 COMP.",
            "01 J PIC 9 COMP.",
            "01 WS-TAB.",
            "   05 WS-ROW OCCURS 3 TIMES.",
            "      10 WS-CELL PIC 9 OCCURS 3 TIMES.",
            "PROCEDURE DIVISION.",
            "    MOVE WS-CELL(I, J) TO I.",
            "    GOBACK.",
        ]
    )
    src = obj["statements"][0]["operands"][0]
    assert src["subscripts"] == ["I", "J"]  # BOTH kept (no get(0) truncation)
