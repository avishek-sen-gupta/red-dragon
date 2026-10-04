"""The bridge serialises ADDRESS OF and NULL as operands in SET, conditions
and CALL USING, instead of glued text."""

from __future__ import annotations

import json
import os

from cobol_asg.subprocess_runner import RealSubprocessRunner
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import to_fixed

_SOURCE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. PTRJSON.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 P USAGE POINTER.",
    "01 X PIC X(2).",
    "LINKAGE SECTION.",
    "01 LK PIC X(2).",
    "PROCEDURE DIVISION USING LK.",
    "    SET P TO ADDRESS OF X.",
    "    SET ADDRESS OF LK TO P.",
    "    SET P TO NULL.",
    "    SET P UP BY 2.",
    "    IF ADDRESS OF LK = NULL",
    "        CALL 'SUB' USING BY VALUE ADDRESS OF X",
    "    END-IF.",
    "    GOBACK.",
]


def _children(node: dict | list | str | int | bool | None) -> list:
    return (
        list(node.values())
        if isinstance(node, dict)
        else (node if isinstance(node, list) else [])
    )


def _statements(node: dict | list | str | int | bool | None, kind: str) -> list[dict]:
    """Every statement of ``kind`` in the bridge JSON, in document order."""
    own = [node] if isinstance(node, dict) and node.get("type") == kind else []
    return own + [
        found for child in _children(node) for found in _statements(child, kind)
    ]


def _ref(name: str, kind: str = "ref") -> dict:
    return {"kind": kind, "name": name, "qualifiers": [], "subscripts": []}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_address_of_and_null_are_structured_operands() -> None:
    jar = os.environ["PROLEAP_BRIDGE_JAR"]
    doc = json.loads(
        RealSubprocessRunner().run(["java", "-jar", jar], to_fixed(_SOURCE))
    )
    sets = [
        (s["targets"], s.get("values"), s.get("value")) for s in _statements(doc, "SET")
    ]
    relation = _statements(doc, "IF")[0]["condition"]["relation"]
    using = _statements(doc, "CALL")[0]["using"][0]

    assert (sets, relation["left"], relation["right"], using) == (
        [
            ([_ref("P")], [_ref("X", "address_of")], None),
            ([_ref("LK", "address_of")], [_ref("P")], None),
            ([_ref("P")], [{"kind": "figurative", "value": "NULL"}], None),
            ([_ref("P")], None, {"kind": "lit", "value": "2"}),
        ],
        _ref("LK", "address_of"),
        {"kind": "figurative", "value": "NULL"},
        {"name": "X", "type": "VALUE", "address_of": True},
    )
