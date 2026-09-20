"""A ref-modified operand's OF/IN qualifier is its own, and a bound's is the bound's.

``red-dragon-64s4`` is the qualifier probe's instance of the family
``red-dragon-pe45`` / ``red-dragon-35do`` / ``red-dragon-twfl`` opened: a walk
that reaches into a reference modifier's bounds and credits what it finds there
to the sliced operand. Two symptoms, one root — ANTLR resolves ``OF GA`` in
``FA OF GA(1:2)`` to the ``inTable`` rule (the parenthesised part belongs to the
qualifier's own ``tableCall``) rather than ``inData``:

* ``MOVE FA OF GA(1:2)`` emitted no ``qualifiers`` key at all — the walk read
  only ``inData``, so every ref-modified or subscripted qualified operand lost
  its qualifier and resolved against the wrong group (or failed to resolve).
* ``MOVE FA OF GA(1:FB OF GB)`` emitted ``["GB"]`` — ``GB`` qualifies the
  BOUND's ``FB``; the walk descended into the bound, and the bare ``FB OF GB``
  there IS an ``inData``, so the bound's qualifier stood in for the operand's.

A collecting walk cannot use the family's post-hoc guard ``boundsTheSliceOf``;
it needs the same rule as a recursion cut — never enter a referenceModifier.
"""

from __future__ import annotations

import json

import pytest

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import to_fixed

_PREAMBLE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. T.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 GA.",
    "   05 FLD PIC X(10) VALUE 'ABCDEFGHIJ'.",
    "01 GB.",
    "   05 FLD PIC X(10) VALUE 'ZZZZZZZZZZ'.",
    "01 NB.",
    "   05 NL PIC 9(4) VALUE 3.",
    "01 D PIC X(10) VALUE SPACES.",
    "01 HT.",
    "   05 TB PIC X(5) OCCURS 3 TIMES.",
    "01 I PIC 9(2) VALUE 1.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
]


def _program(*statement_lines: str) -> list[str]:
    return [
        *_PREAMBLE,
        *(f"    {line}" for line in statement_lines),
        "    STOP RUN.",
    ]


def _statements(bridge_jar: str, *statement_lines: str) -> list[dict]:
    raw = RealSubprocessRunner().run(
        ["java", "-jar", bridge_jar], to_fixed(_program(*statement_lines))
    )
    return json.loads(raw)["paragraphs"][0]["statements"]


def _source_operand(bridge_jar: str, statement_line: str) -> dict:
    return _statements(bridge_jar, statement_line)[0]["operands"][0]


_LIT_1 = {"kind": "lit", "value": "1"}


# ── The bridge JSON shape ────────────────────────────────────────────────────


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_a_literal_bound_leaves_the_operands_qualifier_intact(bridge_jar):
    """The plainer half: no bound to blame, the qualifier vanished outright."""
    assert _source_operand(bridge_jar, "MOVE FLD OF GA(1:2) TO D.") == {
        "name": "FLD",
        "ref_mod_start": _LIT_1,
        "ref_mod_length": {"kind": "lit", "value": "2"},
        "qualifiers": ["GA"],
    }


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_a_qualified_bound_does_not_requalify_the_sliced_operand(bridge_jar):
    """The bound's GB stood in for the operand's GA."""
    assert _source_operand(bridge_jar, "MOVE FLD OF GA(1:NL OF NB) TO D.") == {
        "name": "FLD",
        "ref_mod_start": _LIT_1,
        "ref_mod_length": {"kind": "ref", "name": "NL"},
        "qualifiers": ["GA"],
    }


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_a_qualified_bound_on_an_unqualified_operand_adds_no_qualifier(bridge_jar):
    """Nothing qualifies the slice here; the bound's NB must not leak out."""
    operand = _source_operand(bridge_jar, "MOVE FLD OF GA(1:NL OF NB) TO D.")
    assert operand["qualifiers"] == ["GA"]
    unqualified = _source_operand(bridge_jar, "MOVE D(1:NL OF NB) TO D.")
    assert "qualifiers" not in unqualified


@covers(CobolFeature.GROUP_ITEM)
def test_a_qualified_operand_without_a_ref_mod_still_carries_its_qualifier(bridge_jar):
    assert _source_operand(bridge_jar, "MOVE FLD OF GA TO D.") == {
        "name": "FLD",
        "qualifiers": ["GA"],
    }


@covers(CobolFeature.GROUP_ITEM, CobolFeature.SUBSCRIPT_ACCESS)
@covers(CobolFeature.REFERENCE_MODIFICATION)
def test_a_subscripted_and_qualified_operand_keeps_its_qualifier(bridge_jar):
    operand = _source_operand(bridge_jar, "MOVE TB OF HT(I)(1:2) TO D.")
    assert operand["name"] == "TB"
    assert operand["qualifiers"] == ["HT"]
    assert operand["ref_mod_length"] == {"kind": "lit", "value": "2"}


@covers(CobolFeature.MOVE)
def test_an_unqualified_operand_still_emits_no_qualifiers_key(bridge_jar):
    assert _source_operand(bridge_jar, "MOVE D TO D.") == {"name": "D"}


# ── Guard-rail: CardDemo's bare qualified BMS fields are untouched ───────────


@covers(CobolFeature.GROUP_ITEM)
@pytest.mark.parametrize("group", ["GA", "GB"])
def test_a_bare_qualified_field_keeps_exactly_one_qualifier(bridge_jar, group):
    """COTRN02C's TRNAMTI OF COTRN2AI shape — an inData, not an inTable."""
    assert _source_operand(bridge_jar, f"MOVE FLD OF {group} TO D.")["qualifiers"] == [
        group
    ]
