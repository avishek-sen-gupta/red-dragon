"""Bridge: an ALL literal keeps its ALL in MOVE, VALUE, level-88 VALUE and relations."""

from __future__ import annotations

import json
from collections.abc import Sequence

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration import cobol_helpers

bridge_jar = cobol_helpers.bridge_jar


def _parse(src: Sequence[str], jar: str) -> dict:
    fixed = "\n".join("       " + line for line in src) + "\n"
    return json.loads(RealSubprocessRunner().run(["java", "-jar", jar], fixed))


@covers(CobolFeature.FIGURATIVE_ALL)
def test_bridge_serialises_all_literal_with_its_all(bridge_jar):
    obj = _parse(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. T.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            '01 W2 PIC X(10) VALUE ALL "AB".',
            "01 W3 PIC X(4) VALUE ALL SPACES.",
            "01 DC PIC X(4) VALUE 'BACB'.",
            "   88 DCOK VALUE ALL 'BAC' 'X'.",
            "PROCEDURE DIVISION.",
            '    MOVE ALL "AB" TO W2.',
            "    MOVE ALL QUOTE TO W2.",
            '    IF W2 = ALL "BA" CONTINUE END-IF.',
            "    IF ALL ZEROES = W3 CONTINUE END-IF.",
            "    GOBACK.",
        ],
        bridge_jar,
    )
    fields = {f["name"]: f for f in obj["data_fields"]}
    statements = obj["statements"]
    assert (
        fields["W2"]["value"],
        fields["W2"]["value_is_all"],
        fields["W3"]["value"],
        fields["W3"]["value_is_figurative"],
        "value_is_all" in fields["W3"],
        fields["DC"]["conditions"][0]["values"],
        statements[0]["operands"][0],
        statements[1]["operands"][0],
        statements[2]["condition"]["relation"]["right"],
        statements[3]["condition"]["relation"]["left"],
    ) == (
        "AB",
        True,
        "SPACES",
        True,
        False,
        [{"from": "BAC", "to": "", "all": True}, {"from": "X", "to": ""}],
        {"name": '"AB"', "all": True},
        {"name": "QUOTE"},
        {"kind": "figurative", "value": "ALL", "literal": '"BA"'},
        {"kind": "figurative", "value": "ZEROS"},
    )
