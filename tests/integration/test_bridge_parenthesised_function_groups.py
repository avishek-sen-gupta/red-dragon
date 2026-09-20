"""Bridge JSON shape for a parenthesised group that contains an intrinsic FUNCTION.

``basis : LPARENCHAR arithmeticExpression RPARENCHAR | identifier | literal``.
``serializeBasis`` probed the WHOLE basis subtree for a ``functionCall`` rule so
that a basis which *is* a function call keeps its call + args (red-dragon-ge72).
For a parenthesised basis that probe reached inside the parentheses, found the
nested call, and returned it as the entire group — every other operand and
operator in the group was discarded. ``(FUNCTION LENGTH(M) - N)`` serialized as
just ``FUNCTION LENGTH(M)``.

These tests pin the group's structure, and — because a parenthesis after a data
name is also how COBOL writes a subscript — re-pin the multi-argument /
subscript joins of red-dragon-jscx, which must stay untouched.
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
    "01 M PIC X(40).",
    "01 N PIC 9(4) VALUE 34.",
    "01 O PIC S9(4).",
    "01 A PIC 9(4) VALUE 3.",
    "01 B PIC 9(4) VALUE 7.",
    "01 I PIC 9(2) VALUE 1.",
    "01 G.",
    "   05 X PIC 9(4) OCCURS 7 TIMES.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
]


def _statement(bridge_jar: str, *statement_lines: str) -> dict:
    raw = RealSubprocessRunner().run(
        ["java", "-jar", bridge_jar],
        _fixed(
            [*_PREAMBLE, *(f"    {line}" for line in statement_lines), "    STOP RUN."]
        ),
    )
    return json.loads(raw)["paragraphs"][0]["statements"][0]


def _expression(statement_line: str, bridge_jar: str) -> dict:
    return _statement(bridge_jar, statement_line)["expression"]


_LENGTH_OF_M = {
    "kind": "function",
    "name": "LENGTH",
    "args": [{"kind": "ref", "name": "M"}],
}
_REF_N = {"kind": "ref", "name": "N"}


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_group_keeps_the_operand_after_the_function(bridge_jar):
    """(FUNCTION LENGTH(M) - N) is a subtraction, not a bare LENGTH call."""
    assert _expression("COMPUTE O = (FUNCTION LENGTH(M) - N).", bridge_jar) == {
        "kind": "binop",
        "op": "-",
        "left": _LENGTH_OF_M,
        "right": _REF_N,
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_group_keeps_the_operand_before_the_function(bridge_jar):
    """The FUNCTION need not be the left operand — parenthesising is what was fatal."""
    assert _expression("COMPUTE O = (N - FUNCTION LENGTH(M)).", bridge_jar) == {
        "kind": "binop",
        "op": "-",
        "left": _REF_N,
        "right": _LENGTH_OF_M,
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_group_survives_as_an_operand_of_the_enclosing_expression(bridge_jar):
    """(FUNCTION LENGTH(M) - N) / 2 + 1 keeps the group AND its context."""
    assert _expression("COMPUTE O = (FUNCTION LENGTH(M) - N) / 2 + 1.", bridge_jar) == {
        "kind": "binop",
        "op": "+",
        "left": {
            "kind": "binop",
            "op": "/",
            "left": {"kind": "binop", "op": "-", "left": _LENGTH_OF_M, "right": _REF_N},
            "right": {"kind": "lit", "value": "2"},
        },
        "right": {"kind": "lit", "value": "1"},
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_nested_groups_keep_every_operand(bridge_jar):
    assert _expression("COMPUTE O = ((FUNCTION LENGTH(M) - 1)).", bridge_jar) == {
        "kind": "binop",
        "op": "-",
        "left": _LENGTH_OF_M,
        "right": {"kind": "lit", "value": "1"},
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_group_in_an_if_relation_keeps_every_operand(bridge_jar):
    condition = _statement(
        bridge_jar,
        "IF (FUNCTION LENGTH(M) - N) > 2",
        "    MOVE 1 TO O",
        "END-IF.",
    )["condition"]
    assert condition["relation"]["left"] == {
        "kind": "binop",
        "op": "-",
        "left": _LENGTH_OF_M,
        "right": _REF_N,
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_group_in_a_perform_until_keeps_every_operand(bridge_jar):
    statement = _statement(
        bridge_jar,
        "PERFORM UNTIL N > (FUNCTION LENGTH(M) - 1)",
        "    ADD 1 TO N",
        "END-PERFORM.",
    )
    assert statement["until"]["relation"]["right"] == {
        "kind": "binop",
        "op": "-",
        "left": _LENGTH_OF_M,
        "right": {"kind": "lit", "value": "1"},
    }


# ── Guard-rails: the red-dragon-jscx joins must not regress ────────────────────


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_comma_separated_arguments_stay_two_arguments(bridge_jar):
    """FUNCTION MAX(A, (B)) is a genuine two-argument call."""
    node = _expression("COMPUTE O = FUNCTION MAX(A, (B)).", bridge_jar)
    assert node["name"] == "MAX"
    assert node["args"] == [{"kind": "ref", "name": "A"}, {"kind": "ref", "name": "B"}]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_space_separated_arguments_stay_two_arguments(bridge_jar):
    node = _expression("COMPUTE O = FUNCTION MAX(A B).", bridge_jar)
    assert node["args"] == [{"kind": "ref", "name": "A"}, {"kind": "ref", "name": "B"}]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_parenthesised_arguments_stay_two_arguments(bridge_jar):
    """A parenthesised left operand is never a subscript base."""
    node = _expression("COMPUTE O = FUNCTION MAX((A) (B)).", bridge_jar)
    assert node["args"] == [{"kind": "ref", "name": "A"}, {"kind": "ref", "name": "B"}]


@covers(CobolFeature.SUBSCRIPT_ACCESS, CobolFeature.ARITHMETIC_EXPRESSION)
def test_subscripted_read_in_an_expression_keeps_its_subscript(bridge_jar):
    assert _expression("COMPUTE O = X(I) + 1.", bridge_jar) == {
        "kind": "binop",
        "op": "+",
        "left": {
            "kind": "ref",
            "name": "X",
            "subscripts": [{"kind": "ref", "name": "I"}],
        },
        "right": {"kind": "lit", "value": "1"},
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_subscripted_function_argument_keeps_its_subscript(bridge_jar):
    node = _expression("COMPUTE O = FUNCTION MAX(X(I) B).", bridge_jar)
    assert node["args"][0] == {
        "kind": "ref",
        "name": "X",
        "subscripts": [{"kind": "ref", "name": "I"}],
    }
