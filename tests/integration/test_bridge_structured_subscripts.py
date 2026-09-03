from __future__ import annotations

import json

from interpreter.cobol.features import CobolFeature
from cobol_asg.subprocess_runner import RealSubprocessRunner
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401


def _fixed(lines: list[str]) -> str:
    return "\n".join("       " + line for line in lines) + "\n"


def _parse(src: list[str], bridge_jar: str) -> dict:
    raw = RealSubprocessRunner().run(["java", "-jar", bridge_jar], _fixed(src))
    return json.loads(raw)


@covers(CobolFeature.OCCURS_FIXED)
def test_bridge_emits_bare_name_and_structured_subscript_node(bridge_jar):
    """A subscript is a STRUCTURED expression node ({"kind":...}), not a string —
    the bridge reuses the value-stmt expression serializer (red-dragon-l445)."""
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
        ],
        bridge_jar,
    )
    move = obj["statements"][0]
    src = move["operands"][0]
    assert src["name"] == "WS-ELEM"  # bare base, no "(WS-IDX)"
    subs = src["subscripts"]
    assert len(subs) == 1
    sub = subs[0]
    assert isinstance(sub, dict)  # structured node, NOT a string
    assert sub["kind"] == "ref"
    assert sub["name"] == "WS-IDX"


@covers(CobolFeature.OCCURS_FIXED)
def test_bridge_keeps_all_structured_subscripts_2d(bridge_jar):
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
        ],
        bridge_jar,
    )
    src = obj["statements"][0]["operands"][0]
    subs = src["subscripts"]
    assert len(subs) == 2  # BOTH kept (no get(0) truncation)
    assert all(isinstance(s, dict) and s["kind"] == "ref" for s in subs)
    assert [s["name"] for s in subs] == ["I", "J"]


def _move_operands(src: list[str], bridge_jar: str) -> list[dict]:
    return _parse(src, bridge_jar)["statements"][0]["operands"]


_TABLE_2D = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. T.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-IDX PIC 9(4) COMP.",
    "01 WS-TAB.",
    "   05 WS-ROW OCCURS 5 TIMES.",
    "      10 WS-CELL PIC 9(4) OCCURS 5 TIMES.",
    "PROCEDURE DIVISION.",
]


@covers(CobolFeature.OCCURS_FIXED)
def test_bridge_keeps_both_subscripts_when_a_literal_follows_a_data_name(bridge_jar):
    """`TBL(I, 3)` is TWO subscripts, not one.

    `subscript`'s old `qualifiedDataName integerLiteral?` alternative swallowed
    the trailing literal into the same subscript, and TableCallImpl then kept the
    literal and discarded the data name — so a 2-D reference silently became a
    1-D read of the wrong element (red-dragon-5wp3).
    """
    src = _move_operands(
        _TABLE_2D + ["    MOVE WS-CELL(WS-IDX, 3) TO WS-IDX.", "    GOBACK."],
        bridge_jar,
    )[0]
    assert src["name"] == "WS-CELL"
    subs = src["subscripts"]
    assert len(subs) == 2
    assert subs[0] == {"kind": "ref", "name": "WS-IDX"}
    assert subs[1] == {"kind": "lit", "value": "3"}


@covers(CobolFeature.OCCURS_FIXED)
def test_bridge_keeps_a_relative_subscript_as_one_expression(bridge_jar):
    """`TBL(I + 1)` is ONE subscript carrying a binop, not two subscripts.

    Splitting it inflated a 1-D reference to 2-D, which the lowerer then rejected
    with "subscript count 2 exceeds OCCURS dimensions 1" (red-dragon-5wp3).
    """
    src = _move_operands(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-IDX PIC 9(4) COMP.",
            "01 WS-TAB.",
            "   05 WS-ELEM PIC 9(4) OCCURS 5 TIMES.",
            "PROCEDURE DIVISION.",
            "    MOVE WS-ELEM(WS-IDX + 1) TO WS-IDX.",
            "    GOBACK.",
        ],
        bridge_jar,
    )[0]
    subs = src["subscripts"]
    assert len(subs) == 1
    assert subs[0] == {
        "kind": "binop",
        "op": "+",
        "left": {"kind": "ref", "name": "WS-IDX"},
        "right": {"kind": "lit", "value": "1"},
    }


@covers(CobolFeature.OCCURS_FIXED)
def test_bridge_serialises_an_integer_subscript_as_a_literal(bridge_jar):
    """`TBL(2)` is a literal node, not a reference to a field named "2"."""
    src = _move_operands(
        _TABLE_2D + ["    MOVE WS-CELL(1, 2) TO WS-IDX.", "    GOBACK."],
        bridge_jar,
    )[0]
    assert src["subscripts"] == [
        {"kind": "lit", "value": "1"},
        {"kind": "lit", "value": "2"},
    ]
