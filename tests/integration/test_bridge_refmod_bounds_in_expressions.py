"""Bridge JSON shape for a ref-mod bound reached through an EXPRESSION probe.

``red-dragon-pe45`` fixed the MOVE/STRING operand probe (``findFunctionCallCtx``):
a call sitting under a reference modifier computes a slice BOUND and must not be
returned in place of the sliced operand. The same defect survived at three more
probes, all of which search an operand's subtree and return the nested node:

* ``findFunctionCallCtxInSubtree`` — the arithmetic/relation basis probe, used by
  both ``serializeBasis`` (ASG) and ``serializeBasisCtx`` (grammar context).
  ``COMPUTE O = FUNCTION LENGTH(M(1:FUNCTION LENGTH(M)))`` lost the sliced ``M``
  and both bounds (red-dragon-35do).
* ``findLengthOfSpecialRegister`` at ``serializeFromValue`` and at
  ``serializeBasisCtx`` — the same shape with ``LENGTH OF`` in place of the
  intrinsic call (red-dragon-twfl).

A node reached through a reference modifier belongs to the bound, not to the
operand. These tests pin that distinction at every one of those probes, and
re-pin the guard-rails (red-dragon-jscx multi-argument/subscript joins,
red-dragon-nwm5 parenthesised groups) that must stay untouched.
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
    "01 NUMF PIC 9(6) VALUE 123456.",
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


def _statements(bridge_jar: str, *statement_lines: str) -> list[dict]:
    raw = RealSubprocessRunner().run(
        ["java", "-jar", bridge_jar],
        _fixed(
            [*_PREAMBLE, *(f"    {line}" for line in statement_lines), "    STOP RUN."]
        ),
    )
    return json.loads(raw)["paragraphs"][0]["statements"]


def _expression(bridge_jar: str, statement_line: str) -> dict:
    return _statements(bridge_jar, statement_line)[0]["expression"]


_LIT_1 = {"kind": "lit", "value": "1"}
_LENGTH_OF_M = {
    "kind": "function",
    "name": "LENGTH",
    "args": [{"kind": "ref", "name": "M"}],
}
_LENGTH_OF_N_REGISTER = {"kind": "length_of", "name": "N"}
_SLICED_M = {
    "kind": "ref",
    "name": "M",
    "ref_mod_start": _LIT_1,
    "ref_mod_length": _LENGTH_OF_M,
}
_SLICED_NUMF = {
    "kind": "ref",
    "name": "NUMF",
    "ref_mod_start": _LIT_1,
    "ref_mod_length": _LENGTH_OF_N_REGISTER,
}


# ── red-dragon-35do: findFunctionCallCtxInSubtree, both callers ───────────────


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_function_bound_inside_a_function_argument_keeps_the_sliced_field(bridge_jar):
    """The defect collapsed the argument to the inner LENGTH call."""
    assert _expression(
        bridge_jar, "COMPUTE O = FUNCTION LENGTH(M(1:FUNCTION LENGTH(M)))."
    ) == {"kind": "function", "name": "LENGTH", "args": [_SLICED_M]}


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_function_bound_in_a_relation_operand_keeps_the_sliced_field(bridge_jar):
    """serializeBasis (ASG path): the comparison read a number, not the text."""
    statement = _statements(
        bridge_jar,
        "IF M(1:FUNCTION LENGTH(M)) = 'ABCDEFGHIJ'",
        "  MOVE 'Y' TO D",
        "END-IF.",
    )[0]
    assert statement["condition"]["relation"]["left"] == _SLICED_M


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_function_bound_in_an_arithmetic_operand_keeps_the_sliced_field(bridge_jar):
    assert _expression(bridge_jar, "COMPUTE O = M(1:FUNCTION LENGTH(M)) + 0.") == {
        "kind": "binop",
        "op": "+",
        "left": _SLICED_M,
        "right": {"kind": "lit", "value": "0"},
    }


# ── red-dragon-twfl: the LENGTH OF register at the same two probes ────────────


@covers(CobolFeature.PERFORM_VARYING, CobolFeature.REFERENCE_MODIFICATION)
def test_length_of_bound_in_a_perform_varying_from_keeps_the_sliced_field(bridge_jar):
    """serializeFromValue: varying_from was the bare LENGTH OF register."""
    statement = _statements(
        bridge_jar,
        "PERFORM VARYING I FROM NUMF(1:LENGTH OF N) BY 1 UNTIL I > 3",
        "  CONTINUE",
        "END-PERFORM.",
    )[0]
    assert statement["varying_from"] == _SLICED_NUMF


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_length_of_bound_in_a_function_argument_keeps_the_sliced_field(bridge_jar):
    """serializeBasisCtx: args[0] was the bare LENGTH OF register."""
    node = _expression(bridge_jar, "COMPUTE O = FUNCTION MAX(NUMF(1:LENGTH OF N) 1).")
    assert node["args"][0] == _SLICED_NUMF


@covers(CobolFeature.REFERENCE_MODIFICATION)
def test_length_of_bound_in_a_relation_operand_keeps_the_sliced_field(bridge_jar):
    statement = _statements(
        bridge_jar,
        "IF M(1:LENGTH OF N) = 'ABCD'",
        "  MOVE 'Y' TO D",
        "END-IF.",
    )[0]
    assert statement["condition"]["relation"]["left"] == {
        "kind": "ref",
        "name": "M",
        "ref_mod_start": _LIT_1,
        "ref_mod_length": _LENGTH_OF_N_REGISTER,
    }


@covers(CobolFeature.REFERENCE_MODIFICATION, CobolFeature.SUBSCRIPT_ACCESS)
def test_a_subscript_is_not_a_ref_mod_bound(bridge_jar):
    """T(I)(1:LENGTH OF N) carries both; neither may replace the operand."""
    node = _expression(bridge_jar, "COMPUTE O = FUNCTION MAX(T(I)(1:LENGTH OF N) 1).")
    assert node["args"][0]["name"] == "T"
    assert node["args"][0]["subscripts"] == [{"kind": "ref", "name": "I"}]
    assert node["args"][0]["ref_mod_length"] == _LENGTH_OF_N_REGISTER


# ── Guard-rails: an operand that genuinely IS the nested node stays one ───────


@covers(CobolFeature.REFERENCE_MODIFICATION)
def test_a_plain_length_of_argument_is_still_the_register(bridge_jar):
    node = _expression(bridge_jar, "COMPUTE O = FUNCTION MAX(LENGTH OF N 1).")
    assert node["args"][0] == _LENGTH_OF_N_REGISTER


@covers(CobolFeature.PERFORM_VARYING)
def test_a_plain_length_of_perform_from_is_still_the_register(bridge_jar):
    statement = _statements(
        bridge_jar,
        "PERFORM VARYING I FROM LENGTH OF N BY 1 UNTIL I > 3",
        "  CONTINUE",
        "END-PERFORM.",
    )[0]
    assert statement["varying_from"] == _LENGTH_OF_N_REGISTER


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.REFERENCE_MODIFICATION)
def test_a_function_over_a_ref_modified_argument_stays_a_function(bridge_jar):
    """The ref modifier is the ARGUMENT's; the operand is still the call."""
    node = _expression(bridge_jar, "COMPUTE O = FUNCTION LENGTH(M(1:3)).")
    assert node["kind"] == "function"
    assert node["name"] == "LENGTH"
    assert node["args"][0]["name"] == "M"


@covers(CobolFeature.REFERENCE_MODIFICATION)
def test_a_plain_ref_modified_argument_is_unchanged(bridge_jar):
    node = _expression(bridge_jar, "COMPUTE O = FUNCTION MAX(NUMF(1:N) 1).")
    assert node["args"][0] == {
        "kind": "ref",
        "name": "NUMF",
        "ref_mod_start": _LIT_1,
        "ref_mod_length": {"kind": "ref", "name": "N"},
    }


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_comma_separated_arguments_stay_two_arguments(bridge_jar):
    node = _expression(bridge_jar, "COMPUTE O = FUNCTION MAX(A, (B)).")
    assert node["args"] == [{"kind": "ref", "name": "A"}, {"kind": "ref", "name": "B"}]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_space_separated_arguments_stay_two_arguments(bridge_jar):
    node = _expression(bridge_jar, "COMPUTE O = FUNCTION MAX(A B).")
    assert node["args"] == [{"kind": "ref", "name": "A"}, {"kind": "ref", "name": "B"}]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_parenthesised_arguments_stay_two_arguments(bridge_jar):
    node = _expression(bridge_jar, "COMPUTE O = FUNCTION MAX((A) (B)).")
    assert node["args"] == [{"kind": "ref", "name": "A"}, {"kind": "ref", "name": "B"}]


@covers(CobolFeature.SUBSCRIPT_ACCESS, CobolFeature.ARITHMETIC_EXPRESSION)
def test_subscripted_read_in_an_expression_keeps_its_subscript(bridge_jar):
    assert _expression(bridge_jar, "COMPUTE O = X(I) + 1.") == {
        "kind": "binop",
        "op": "+",
        "left": {
            "kind": "ref",
            "name": "X",
            "subscripts": [{"kind": "ref", "name": "I"}],
        },
        "right": _LIT_1,
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.SUBSCRIPT_ACCESS)
def test_subscripted_function_argument_keeps_its_subscript(bridge_jar):
    node = _expression(bridge_jar, "COMPUTE O = FUNCTION MAX(X(I) B).")
    assert node["args"][0] == {
        "kind": "ref",
        "name": "X",
        "subscripts": [{"kind": "ref", "name": "I"}],
    }


@covers(CobolFeature.INTRINSIC_FUNCTION, CobolFeature.ARITHMETIC_EXPRESSION)
def test_parenthesised_group_keeps_every_operand(bridge_jar):
    assert _expression(bridge_jar, "COMPUTE O = (FUNCTION LENGTH(M) - N).") == {
        "kind": "binop",
        "op": "-",
        "left": _LENGTH_OF_M,
        "right": {"kind": "ref", "name": "N"},
    }
