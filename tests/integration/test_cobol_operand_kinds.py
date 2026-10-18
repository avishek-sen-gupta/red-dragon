"""Every operand states its kind: the bridge writes ref, lit or figurative, and
lowering dispatches on it rather than guessing from the text."""

from __future__ import annotations

import json
import os

import pytest

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    first_region,
    run_cobol,
    to_fixed,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


_KINDS = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. KINDS.",
    "ENVIRONMENT DIVISION.",
    "INPUT-OUTPUT SECTION.",
    "FILE-CONTROL.",
    "    SELECT F ASSIGN TO 'OUT'.",
    "DATA DIVISION.",
    "FILE SECTION.",
    "FD F.",
    "01 R PIC X(4).",
    "WORKING-STORAGE SECTION.",
    "01 W PIC X(10).",
    "01 N PIC 9(4).",
    "PROCEDURE DIVISION.",
    "    MOVE 'AB' TO W.",
    "    MOVE SPACES TO W.",
    "    MOVE ALL '*' TO W.",
    "    DISPLAY 'HI' ZERO W.",
    "    ADD 12 ZERO TO N.",
    "    STRING 'X' W DELIMITED BY SIZE INTO W.",
    "    INITIALIZE W REPLACING ALPHANUMERIC DATA BY 'Q'.",
    "    CALL 'SUB' USING BY CONTENT 'C' BY VALUE 5 BY CONTENT ZERO.",
    "    WRITE R FROM 'ABCD'.",
    "    GOBACK.",
]


def _lit(name: str) -> dict:
    return {"kind": "lit", "name": name}


def _figurative(name: str) -> dict:
    return {"kind": "figurative", "name": name}


_W = {"kind": "ref", "name": "W"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_bridge_states_each_operands_kind() -> None:
    jar = os.environ["PROLEAP_BRIDGE_JAR"]
    doc = json.loads(
        RealSubprocessRunner().run(["java", "-jar", jar], to_fixed(_KINDS))
    )
    move_a, move_spaces, move_all, display, add, string, init, call, write = doc[
        "statements"
    ][:9]

    assert (
        move_a["operands"],
        move_spaces["operands"][0],
        move_all["operands"][0],
        display["operands"],
        add["operands"],
        [sending["value"] for sending in string["sendings"]],
        init["replacing"][0]["by"],
        call["using"],
        write["from_field"],
    ) == (
        [_lit("'AB'"), _W],
        _figurative("SPACES"),
        _lit("'*'") | {"all": True},
        [_lit("'HI'"), _figurative("ZERO"), _W],
        [_lit("12") | {"numeric": True}, _figurative("ZERO")],
        [_lit("'X'"), _W],
        _lit("'Q'"),
        [
            {"type": "CONTENT", "is_literal": True} | _lit("'C'"),
            {"type": "VALUE", "is_literal": True, "numeric": True} | _lit("5"),
            {"type": "CONTENT", "is_literal": True} | _figurative("ZERO"),
        ],
        _lit("'ABCD'"),
    )


@covers(CobolFeature.STRING_VERB)
def test_an_undeclared_data_name_is_an_error_not_literal_text() -> None:
    """A data name is resolved against the DATA DIVISION; one the program does
    not declare is not taken as a literal spelled like it. Literals and
    figurative constants beside it keep their values."""
    declared = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. KINDS2.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 W PIC X(10) VALUE SPACES.",
        "01 V PIC X(4) VALUE 'ABCD'.",
        "PROCEDURE DIVISION.",
        "    STRING 'X' V QUOTE DELIMITED BY SIZE INTO W.",
        "    STOP RUN.",
    ]
    undeclared = [
        *declared[:7],
        "    STRING WS-NOPE DELIMITED BY SIZE INTO W.",
        *declared[8:],
    ]

    region = first_region(run_cobol(declared))

    assert bytes(region[0:10]).decode("cp037") == 'XABCD"    '
    with pytest.raises(KeyError, match="Field 'WS-NOPE' not found"):
        run_cobol(undeclared)
