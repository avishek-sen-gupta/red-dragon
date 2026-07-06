from __future__ import annotations

import json

from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.integration.cobol_helpers import bridge_jar


def _fixed(lines: list[str]) -> str:
    return "\n".join("       " + line for line in lines) + "\n"


def _parse(src: list[str], jar: str) -> dict:
    raw = RealSubprocessRunner().run(["java", "-jar", jar], _fixed(src))
    return json.loads(raw)


def _first_statement(obj: dict) -> dict:
    return obj["statements"][0]


def test_unstring_emits_multiple_delimiters_as_a_list(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-SRC PIC X(10).",
            "01 WS-F1 PIC X(5).",
            "01 WS-F2 PIC X(5).",
            "PROCEDURE DIVISION.",
            "    UNSTRING WS-SRC DELIMITED BY ',' OR ';' INTO WS-F1 WS-F2.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    stmt = _first_statement(obj)
    assert stmt["delimiters"] == ["','", "';'"]


def test_unstring_emits_pointer_and_tallying_target(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-SRC PIC X(10).",
            "01 WS-F1 PIC X(5).",
            "01 WS-PTR PIC 9(4).",
            "01 WS-CNT PIC 9(4).",
            "PROCEDURE DIVISION.",
            "    UNSTRING WS-SRC DELIMITED BY ',' INTO WS-F1",
            "        WITH POINTER WS-PTR TALLYING IN WS-CNT.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    stmt = _first_statement(obj)
    assert stmt["pointer"] == "WS-PTR"
    assert stmt["tallying_target"] == "WS-CNT"


def test_string_emits_pointer(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-A PIC X(5).",
            "01 WS-DST PIC X(10).",
            "01 WS-PTR PIC 9(4).",
            "PROCEDURE DIVISION.",
            "    STRING WS-A DELIMITED BY SIZE INTO WS-DST",
            "        WITH POINTER WS-PTR.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    stmt = _first_statement(obj)
    assert stmt["pointer"] == "WS-PTR"


def test_inspect_emits_tallying_groups_for_multiple_targets(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-SRC PIC X(10).",
            "01 WS-CNT-A PIC 9(4).",
            "01 WS-CNT-B PIC 9(4).",
            "PROCEDURE DIVISION.",
            "    INSPECT WS-SRC TALLYING WS-CNT-A FOR ALL 'A'",
            "        WS-CNT-B FOR ALL 'B'.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    stmt = _first_statement(obj)
    groups = stmt["tallying_groups"]
    assert len(groups) == 2
    assert groups[0]["target"] == "WS-CNT-A"
    assert groups[0]["patterns"][0]["pattern"] == "'A'"
    assert groups[1]["target"] == "WS-CNT-B"
    assert groups[1]["patterns"][0]["pattern"] == "'B'"


def test_inspect_tallying_emits_before_initial_boundary(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-SRC PIC X(10).",
            "01 WS-CNT PIC 9(4).",
            "PROCEDURE DIVISION.",
            "    INSPECT WS-SRC TALLYING WS-CNT FOR ALL 'A'",
            "        BEFORE INITIAL '.'.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    stmt = _first_statement(obj)
    pattern = stmt["tallying_groups"][0]["patterns"][0]
    assert pattern["before"] == "'.'"


def test_inspect_replacing_emits_after_initial_boundary(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-SRC PIC X(10).",
            "PROCEDURE DIVISION.",
            "    INSPECT WS-SRC REPLACING ALL 'A' BY 'Z' AFTER INITIAL '.'.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    stmt = _first_statement(obj)
    replacing = stmt["replacings"][0]
    assert replacing["after"] == "'.'"
