from __future__ import annotations

import json

from cobol_asg.subprocess_runner import RealSubprocessRunner
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401


def _fixed(lines: list[str]) -> str:
    return "\n".join("       " + line for line in lines) + "\n"


def _parse(src: list[str], jar: str) -> dict:
    raw = RealSubprocessRunner().run(["java", "-jar", jar], _fixed(src))
    return json.loads(raw)


def _first_statement(obj: dict) -> dict:
    return obj["statements"][0]


def test_unstring_emits_delimiters_with_all_and_receivers_with_their_items(
    bridge_jar,
):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-SRC PIC X(10).",
            "01 WS-T. 02 WS-D PIC X OCCURS 3.",
            "01 WS-I PIC 9.",
            "01 WS-F1 PIC X(5).",
            "01 WS-F2 PIC X(5).",
            "01 WS-DL PIC X.",
            "01 WS-CT PIC 99.",
            "PROCEDURE DIVISION.",
            "    UNSTRING WS-SRC DELIMITED BY ALL '0' OR ';' OR ALL SPACE",
            "        OR WS-D (WS-I)",
            "        INTO WS-F1 DELIMITER IN WS-DL COUNT IN WS-CT WS-F2.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    stmt = _first_statement(obj)
    assert (stmt["delimiters"], stmt["into"]) == (
        [
            {"operand": {"name": "'0'"}, "all": True},
            {"operand": {"name": "';'"}},
            {"operand": {"name": "SPACE"}, "all": True},
            {
                "operand": {
                    "name": "WS-D",
                    "subscripts": [{"kind": "ref", "name": "WS-I"}],
                }
            },
        ],
        [
            {
                "target": {"name": "WS-F1"},
                "delimiter_in": {"name": "WS-DL"},
                "count_in": {"name": "WS-CT"},
            },
            {"target": {"name": "WS-F2"}},
        ],
    )


def test_unstring_emits_pointer_and_tallying_target(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-SRC PIC X(10).",
            "01 WS-F1 PIC X(5).",
            "01 WS-P. 02 WS-PTR PIC 9(4).",
            "01 WS-C. 02 WS-CNT PIC 9(4).",
            "PROCEDURE DIVISION.",
            "    UNSTRING WS-SRC DELIMITED BY ',' INTO WS-F1",
            "        WITH POINTER WS-PTR OF WS-P TALLYING IN WS-CNT IN WS-C.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    stmt = _first_statement(obj)
    assert (stmt["pointer"], stmt["tallying_target"]) == (
        {"name": "WS-PTR", "qualifiers": ["WS-P"]},
        {"name": "WS-CNT", "qualifiers": ["WS-C"]},
    )


def test_string_emits_pointer_and_delimiter_operands(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-A PIC X(5).",
            "01 WS-T. 02 WS-D PIC X OCCURS 3.",
            "01 WS-I PIC 9.",
            "01 WS-DST PIC X(10).",
            "01 WS-PTR PIC 9(4).",
            "PROCEDURE DIVISION.",
            "    STRING WS-A DELIMITED BY SIZE SPACE DELIMITED BY WS-D (WS-I)",
            "        'X' DELIMITED BY QUOTE INTO WS-DST",
            "        WITH POINTER WS-PTR.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    stmt = _first_statement(obj)
    assert (stmt["pointer"], stmt["sendings"]) == (
        {"name": "WS-PTR"},
        [
            {"value": {"name": "WS-A"}},
            {
                "value": {"name": "SPACE"},
                "delimiter": {
                    "name": "WS-D",
                    "subscripts": [{"kind": "ref", "name": "WS-I"}],
                },
            },
            {"value": {"name": "'X'"}, "delimiter": {"name": "QUOTE"}},
        ],
    )


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
    assert groups == [
        {
            "target": {"name": "WS-CNT-A"},
            "patterns": [{"mode": "ALL", "pattern": {"name": "'A'"}}],
        },
        {
            "target": {"name": "WS-CNT-B"},
            "patterns": [{"mode": "ALL", "pattern": {"name": "'B'"}}],
        },
    ]


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
    assert pattern["before"] == {"name": "'.'"}


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
    assert replacing["after"] == {"name": "'.'"}


def test_inspect_emits_every_phrase_form_in_written_order(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 W PIC X(10).",
            "01 T. 02 E PIC X OCCURS 5 INDEXED BY IX.",
            "01 C PIC 9 OCCURS 3.",
            "01 I PIC 9.",
            "PROCEDURE DIVISION.",
            "    INSPECT W TALLYING C (I) FOR CHARACTERS AFTER 'W'",
            "        ALL 'A' BEFORE 'X' ALL E (IX) ALL 'D'",
            "        REPLACING FIRST 'A' BY 'O' ALL 'C' BY '2'",
            "        CHARACTERS BY 'Z' BEFORE 'Q' AFTER 'R'.",
            "    INSPECT W CONVERTING 'AU' TO '23' BEFORE 'B' AFTER 'Q'.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    combined, converting = obj["statements"][0], obj["statements"][1]
    index_ref = [{"kind": "ref", "name": "I"}]
    assert (
        combined["inspect_type"],
        combined["tallying_groups"],
        combined["replacings"],
    ) == (
        "TALLYING_REPLACING",
        [
            {
                "target": {"name": "C", "subscripts": index_ref},
                "patterns": [
                    {"mode": "CHARACTERS", "after": {"name": "'W'"}},
                    {
                        "mode": "ALL",
                        "pattern": {"name": "'A'"},
                        "before": {"name": "'X'"},
                    },
                    {
                        "mode": "ALL",
                        "pattern": {
                            "name": "E",
                            "subscripts": [{"kind": "ref", "name": "IX"}],
                        },
                    },
                    {"mode": "ALL", "pattern": {"name": "'D'"}},
                ],
            }
        ],
        [
            {"mode": "FIRST", "from": {"name": "'A'"}, "to": {"name": "'O'"}},
            {"mode": "ALL", "from": {"name": "'C'"}, "to": {"name": "'2'"}},
            {
                "mode": "CHARACTERS",
                "to": {"name": "'Z'"},
                "before": {"name": "'Q'"},
                "after": {"name": "'R'"},
            },
        ],
    )
    assert (
        converting["converting_from"],
        converting["converting_to"],
        converting["before"],
        converting["after"],
    ) == ({"name": "'AU'"}, {"name": "'23'"}, {"name": "'B'"}, {"name": "'Q'"})
