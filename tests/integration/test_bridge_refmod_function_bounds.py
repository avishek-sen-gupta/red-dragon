"""Bridge JSON shape for an intrinsic FUNCTION used as a reference-modifier bound.

``M(1:FUNCTION LENGTH(M))`` is a slice of ``M`` whose length happens to be
computed by a function. The MOVE/STRING operand serializers probed the operand's
whole grammar subtree for a ``functionCall`` rule and returned the call **in
place of** the ref-modified identifier, so the base field and both slice bounds
were discarded and the statement read a number where text belonged
(red-dragon-pe45).

A function call reached through a reference modifier belongs to the bound, not
to the operand. These tests pin that distinction, and re-pin the multi-argument
/ subscript joins (red-dragon-jscx) and the parenthesised group (red-dragon-nwm5)
that must stay untouched.
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
    "01 M PIC X(10) VALUE 'ABCDEFGHIJ'.",
    "01 N PIC 9(4) VALUE 4.",
    "01 D PIC X(10).",
    "01 O PIC S9(4).",
    "01 A PIC 9(4) VALUE 3.",
    "01 B PIC 9(4) VALUE 7.",
    "01 I PIC 9(2) VALUE 1.",
    "01 G.",
    "   05 X PIC 9(4) OCCURS 7 TIMES.",
    "01 H.",
    "   05 T PIC X(5) OCCURS 3 TIMES.",
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


def _move_source(bridge_jar: str, statement_line: str) -> dict:
    return _statement(bridge_jar, statement_line)["operands"][0]


_LENGTH_OF_M = {
    "kind": "function",
    "name": "LENGTH",
    "args": [{"kind": "ref", "name": "M"}],
}
_LIT_1 = {"kind": "lit", "value": "1"}


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_function_as_the_length_bound_keeps_the_sliced_field(bridge_jar):
    """The defect returned the bare LENGTH call — M and the slice were gone."""
    assert _move_source(bridge_jar, "MOVE M(1:FUNCTION LENGTH(M)) TO D.") == {
        "name": "M",
        "ref_mod_start": _LIT_1,
        "ref_mod_length": _LENGTH_OF_M,
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_parenthesised_bound_keeps_the_sliced_field_and_the_whole_group(bridge_jar):
    assert _move_source(bridge_jar, "MOVE M(1:(FUNCTION LENGTH(M) - 1)) TO D.") == {
        "name": "M",
        "ref_mod_start": _LIT_1,
        "ref_mod_length": {
            "kind": "binop",
            "op": "-",
            "left": _LENGTH_OF_M,
            "right": _LIT_1,
        },
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_function_in_the_start_position_keeps_the_sliced_field(bridge_jar):
    assert _move_source(bridge_jar, "MOVE M(FUNCTION LENGTH(N):2) TO D.") == {
        "name": "M",
        "ref_mod_start": {
            "kind": "function",
            "name": "LENGTH",
            "args": [{"kind": "ref", "name": "N"}],
        },
        "ref_mod_length": {"kind": "lit", "value": "2"},
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_nested_function_inside_the_bound_keeps_the_sliced_field(bridge_jar):
    source = _move_source(
        bridge_jar, "MOVE M(1:FUNCTION MAX(FUNCTION LENGTH(M) A)) TO D."
    )
    assert source["name"] == "M"
    assert source["ref_mod_length"]["name"] == "MAX"
    assert source["ref_mod_length"]["args"][0] == _LENGTH_OF_M


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_string_sending_item_keeps_the_sliced_field(bridge_jar):
    statement = _statement(
        bridge_jar, "STRING M(1:FUNCTION LENGTH(M)) DELIMITED BY SIZE INTO D."
    )
    assert statement["sendings"][0]["value"] == {
        "name": "M",
        "ref_mod_start": _LIT_1,
        "ref_mod_length": _LENGTH_OF_M,
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_subscripted_element_that_is_also_ref_modified(bridge_jar):
    """A subscript and a reference modifier are different constructs; keep both."""
    source = _move_source(bridge_jar, "MOVE T(I)(1:FUNCTION LENGTH(M)) TO D.")
    assert source["name"] == "T"
    assert source["subscripts"] == [{"kind": "ref", "name": "I"}]
    assert source["ref_mod_start"] == _LIT_1
    assert source["ref_mod_length"] == _LENGTH_OF_M


# ── Guard-rails: an operand that genuinely IS a function must stay one ─────────


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_a_function_over_a_ref_modified_argument_stays_a_function(bridge_jar):
    """The ref modifier is the ARGUMENT's; the operand is still the call."""
    source = _move_source(bridge_jar, "MOVE FUNCTION UPPER-CASE(M(1:3)) TO D.")
    assert source["kind"] == "function"
    assert source["name"] == "UPPER-CASE"


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_a_plain_function_source_stays_a_function(bridge_jar):
    source = _move_source(bridge_jar, "MOVE FUNCTION UPPER-CASE(M) TO D.")
    assert source == {
        "kind": "function",
        "name": "UPPER-CASE",
        "args": [{"kind": "ref", "name": "M"}],
    }


@covers(CobolFeature.REFERENCE_MODIFICATION)
def test_a_plain_ref_modified_source_is_unchanged(bridge_jar):
    assert _move_source(bridge_jar, "MOVE M(1:N) TO D.") == {
        "name": "M",
        "ref_mod_start": _LIT_1,
        "ref_mod_length": {"kind": "ref", "name": "N"},
    }


# ── Guard-rails: red-dragon-jscx / red-dragon-nwm5 must not regress ───────────


def _expression(statement_line: str, bridge_jar: str) -> dict:
    return _statement(bridge_jar, statement_line)["expression"]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_comma_separated_arguments_stay_two_arguments(bridge_jar):
    node = _expression("COMPUTE O = FUNCTION MAX(A, (B)).", bridge_jar)
    assert node["args"] == [{"kind": "ref", "name": "A"}, {"kind": "ref", "name": "B"}]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_space_separated_arguments_stay_two_arguments(bridge_jar):
    node = _expression("COMPUTE O = FUNCTION MAX(A B).", bridge_jar)
    assert node["args"] == [{"kind": "ref", "name": "A"}, {"kind": "ref", "name": "B"}]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_parenthesised_arguments_stay_two_arguments(bridge_jar):
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


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_parenthesised_group_keeps_every_operand(bridge_jar):
    assert _expression("COMPUTE O = (FUNCTION LENGTH(M) - N).", bridge_jar) == {
        "kind": "binop",
        "op": "-",
        "left": _LENGTH_OF_M,
        "right": {"kind": "ref", "name": "N"},
    }
