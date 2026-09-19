"""Bridge JSON shape for subscripted intrinsic-FUNCTION arguments (red-dragon).

ProLeap's `functionCall` rule is ambiguous for `FUNCTION f(TBL(I))`: `identifier`
lists `qualifiedDataName` before `tableCall`, and `(I)` is itself a legal
parenthesised `basis`, so ANTLR's lowest-viable-alternative resolution yields TWO
`argument` contexts (`TBL` and `(I)`) rather than one subscripted `tableCall`.
The grammar is vendored ProLeap, so the re-join belongs to the serializer.

These tests pin both halves of that re-join: the paren group must be re-attached
to the identifier it subscripts, and a genuinely multi-argument call
(`FUNCTION MAX(A, (B))` — comma-separated, so NOT a subscript) must survive
untouched.
"""

from __future__ import annotations

import json

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401


def _fixed(lines: list[str]) -> str:
    return "\n".join("       " + line for line in lines) + "\n"


_PREAMBLE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. T.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 I PIC 9(2) VALUE 1.",
    "01 J PIC 9(2) VALUE 1.",
    "01 A PIC 9(4) VALUE 3.",
    "01 B PIC 9(4) VALUE 7.",
    "01 N PIC 9(4).",
    "01 D PIC X(5).",
    "01 G.",
    "   05 TX PIC X(5) OCCURS 7 TIMES.",
    "01 M2.",
    "   05 R2 OCCURS 3 TIMES.",
    "      10 X2 PIC X(5) OCCURS 4 TIMES.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
]


def _function_node(statement_line: str, bridge_jar: str) -> dict:
    raw = RealSubprocessRunner().run(
        ["java", "-jar", bridge_jar],
        _fixed([*_PREAMBLE, f"    {statement_line}", "    STOP RUN."]),
    )
    statement = json.loads(raw)["paragraphs"][0]["statements"][0]
    return statement.get("expression") or statement["operands"][0]


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_variable_subscript_rejoined_to_its_identifier(bridge_jar):
    """FUNCTION TRIM(TX(I)) is ONE argument carrying a structured subscript."""
    node = _function_node("MOVE FUNCTION TRIM(TX(I)) TO D.", bridge_jar)
    assert node["name"] == "TRIM"
    assert len(node["args"]) == 1
    arg = node["args"][0]
    assert arg["kind"] == "ref"
    assert arg["name"] == "TX"
    assert arg["subscripts"] == [{"kind": "ref", "name": "I"}]


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_literal_subscript_rejoined_to_its_identifier(bridge_jar):
    node = _function_node("MOVE FUNCTION TRIM(TX(5)) TO D.", bridge_jar)
    assert len(node["args"]) == 1
    assert node["args"][0]["name"] == "TX"
    assert node["args"][0]["subscripts"] == [{"kind": "lit", "value": "5"}]


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_arithmetic_subscript_rejoined_to_its_identifier(bridge_jar):
    node = _function_node("MOVE FUNCTION TRIM(TX(I + 1)) TO D.", bridge_jar)
    assert len(node["args"]) == 1
    arg = node["args"][0]
    assert arg["name"] == "TX"
    assert len(arg["subscripts"]) == 1
    assert arg["subscripts"][0]["kind"] == "binop"


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_two_dimensional_subscripts_survive_as_structured_nodes(bridge_jar):
    """A comma keeps ProLeap on the tableCall alternative, but the serializer
    still has to emit the indices instead of gluing them into the name."""
    node = _function_node("MOVE FUNCTION TRIM(X2(I, J)) TO D.", bridge_jar)
    assert len(node["args"]) == 1
    arg = node["args"][0]
    assert arg["name"] == "X2"
    assert arg["subscripts"] == [
        {"kind": "ref", "name": "I"},
        {"kind": "ref", "name": "J"},
    ]


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_space_separated_two_dimensional_subscripts(bridge_jar):
    node = _function_node("MOVE FUNCTION TRIM(X2(I J)) TO D.", bridge_jar)
    arg = node["args"][0]
    assert arg["name"] == "X2"
    assert arg["subscripts"] == [
        {"kind": "ref", "name": "I"},
        {"kind": "ref", "name": "J"},
    ]


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_nested_function_argument_keeps_its_subscript(bridge_jar):
    node = _function_node(
        "MOVE FUNCTION UPPER-CASE(FUNCTION TRIM(TX(I))) TO D.", bridge_jar
    )
    assert node["name"] == "UPPER-CASE"
    inner = node["args"][0]
    assert inner["kind"] == "function"
    assert inner["name"] == "TRIM"
    assert inner["args"] == [
        {"kind": "ref", "name": "TX", "subscripts": [{"kind": "ref", "name": "I"}]}
    ]


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_several_subscripted_arguments_each_keep_their_own_index(bridge_jar):
    node = _function_node("COMPUTE N = FUNCTION MAX(TX(I) TX(J)).", bridge_jar)
    assert [arg["name"] for arg in node["args"]] == ["TX", "TX"]
    assert node["args"][0]["subscripts"] == [{"kind": "ref", "name": "I"}]
    assert node["args"][1]["subscripts"] == [{"kind": "ref", "name": "J"}]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_genuine_two_argument_call_is_not_mangled(bridge_jar):
    node = _function_node("COMPUTE N = FUNCTION MAX(A B).", bridge_jar)
    assert node["args"] == [
        {"kind": "ref", "name": "A"},
        {"kind": "ref", "name": "B"},
    ]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_comma_separated_parenthesised_argument_is_not_a_subscript(bridge_jar):
    """`FUNCTION MAX(A, (B))` is two arguments — the COMMA forbids the re-join.
    Without the comma the same token sequence IS a subscripted read, so the
    serializer must discriminate on the separator, not on the paren alone."""
    node = _function_node("COMPUTE N = FUNCTION MAX(A, (B)).", bridge_jar)
    assert len(node["args"]) == 2
    assert node["args"][0] == {"kind": "ref", "name": "A"}
    assert "subscripts" not in node["args"][0]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_parenthesised_first_argument_is_never_a_subscript_base(bridge_jar):
    """`FUNCTION MAX((A) (B))` — a parenthesised expression cannot be subscripted."""
    node = _function_node("COMPUTE N = FUNCTION MAX((A) (B)).", bridge_jar)
    assert len(node["args"]) == 2
    assert "subscripts" not in node["args"][0]
    assert "subscripts" not in node["args"][1]
