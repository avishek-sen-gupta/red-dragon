"""An EVALUATE subject that is more than a name must survive as a reference.

``red-dragon-sfih``. The subject crossed the bridge as a flat STRING, so a
reference-modified subject could not survive it at all: ``EVALUATE FA(1:2)``
arrived as the name ``"FA(1:2)"``, which resolves to no field and was compared
as a literal, and ``EVALUATE FA OF GA(1:2)`` arrived as the leaf ``"FA"``,
which resolves the WHOLE field rather than the slice. Both silent.

The subject now also travels as ``subject_ref`` -- the structured ref node the
operands already get -- whenever it carries a slice, a subscript or a
qualifier, and the Python side reads that node instead of the name. A subject
that IS a plain name keeps the string alone, so nothing else moves. This is the
move red-dragon-74qu made for expression operands.
"""

from __future__ import annotations

import json

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned,
    first_region,
    run_cobol,
    to_fixed,
)

_PREAMBLE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. T.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 GA.",
    "   05 FA PIC X(10) VALUE 'ABCDEFGHIJ'.",
    "01 GB.",
    "   05 FA PIC X(10) VALUE 'ZZZZZZZZZZ'.",
    "01 HT.",
    "   05 TB PIC X(2) OCCURS 3 TIMES.",
    "01 WS-T PIC X(10) VALUE 'ABCDEFGHIJ'.",
    "01 WS-A PIC X(2) VALUE 'AB'.",
    "01 I PIC 9(2) VALUE 2.",
    "01 D PIC 9(4) VALUE 0.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
]

_D = 40


def _program(*statement_lines: str) -> list[str]:
    return [
        *_PREAMBLE,
        *(f"    {line}" for line in statement_lines),
        "    STOP RUN.",
    ]


def _statement(bridge_jar: str, *statement_lines: str) -> dict:
    raw = RealSubprocessRunner().run(
        ["java", "-jar", bridge_jar], to_fixed(_program(*statement_lines))
    )
    return json.loads(raw)["paragraphs"][0]["statements"][0]


def _evaluate(subject: str, *extra: str) -> int:
    region = first_region(
        run_cobol(
            _program(
                *extra,
                f"EVALUATE {subject}",
                "   WHEN 'AB' MOVE 1 TO D",
                "   WHEN 'ZZ' MOVE 2 TO D",
                "   WHEN OTHER MOVE 9 TO D",
                "END-EVALUATE.",
            )
        )
    )
    return decode_zoned_unsigned(region, _D, 4)


_SHAPE = (
    "EVALUATE WS-T(1:2)",
    "   WHEN 'AB' MOVE 1 TO D",
    "   WHEN OTHER MOVE 9 TO D",
    "END-EVALUATE.",
)


# -- The bridge JSON shape ---------------------------------------------------


@covers(CobolFeature.EVALUATE, CobolFeature.REFERENCE_MODIFICATION)
def test_a_sliced_subject_travels_as_a_structured_ref(bridge_jar):
    stmt = _statement(bridge_jar, *_SHAPE)
    assert stmt["subject_ref"] == {
        "kind": "ref",
        "name": "WS-T",
        "ref_mod_start": {"kind": "lit", "value": "1"},
        "ref_mod_length": {"kind": "lit", "value": "2"},
    }


@covers(CobolFeature.EVALUATE, CobolFeature.GROUP_ITEM)
def test_a_qualified_sliced_subject_keeps_both_qualifier_and_slice(bridge_jar):
    stmt = _statement(
        bridge_jar,
        "EVALUATE FA OF GA(1:2)",
        "   WHEN 'AB' MOVE 1 TO D",
        "END-EVALUATE.",
    )
    assert stmt["subject_ref"] == {
        "kind": "ref",
        "name": "FA",
        "ref_mod_start": {"kind": "lit", "value": "1"},
        "ref_mod_length": {"kind": "lit", "value": "2"},
        "qualifiers": ["GA"],
    }


@covers(CobolFeature.EVALUATE, CobolFeature.SUBSCRIPT_ACCESS)
def test_a_subscripted_subject_keeps_its_subscript(bridge_jar):
    stmt = _statement(
        bridge_jar,
        "EVALUATE TB OF HT(I)",
        "   WHEN 'AB' MOVE 1 TO D",
        "END-EVALUATE.",
    )
    assert stmt["subject_ref"] == {
        "kind": "ref",
        "name": "TB",
        "subscripts": [{"kind": "ref", "name": "I"}],
        "qualifiers": ["HT"],
    }


@covers(CobolFeature.EVALUATE)
def test_a_plain_name_subject_stays_a_name(bridge_jar):
    """Nothing a name cannot carry: the string subject is untouched and no
    structured node is emitted, so no existing program's lowering moves."""
    stmt = _statement(
        bridge_jar,
        "EVALUATE WS-A",
        "   WHEN 'AB' MOVE 1 TO D",
        "END-EVALUATE.",
    )
    assert stmt["subject"] == "WS-A"
    assert "subject_ref" not in stmt


@covers(CobolFeature.EVALUATE)
def test_an_evaluate_true_subject_stays_a_name(bridge_jar):
    stmt = _statement(
        bridge_jar,
        "EVALUATE TRUE",
        "   WHEN WS-A = 'AB' MOVE 1 TO D",
        "END-EVALUATE.",
    )
    assert stmt["subject"] == "TRUE"
    assert "subject_ref" not in stmt


# -- The branch the program actually takes -----------------------------------


@covers(CobolFeature.EVALUATE, CobolFeature.REFERENCE_MODIFICATION)
def test_a_sliced_subject_matches_on_the_slice():
    assert _evaluate("FA OF GA(1:2)") == 1
    assert _evaluate("FA OF GB(1:2)") == 2


@covers(CobolFeature.EVALUATE, CobolFeature.REFERENCE_MODIFICATION)
def test_an_unqualified_sliced_subject_matches_on_the_slice():
    """The bead's first spelling: "WS-T(1:2)" resolves to no field at all, so
    the subject was parsed as a literal and nothing but WHEN OTHER matched."""
    assert _evaluate("WS-T(1:2)") == 1
    assert _evaluate("WS-T(2:2)") == 9


@covers(CobolFeature.EVALUATE, CobolFeature.SUBSCRIPT_ACCESS)
def test_a_subscripted_subject_matches_on_its_occurrence():
    fill = [
        "MOVE 'ZZ' TO TB OF HT(1).",
        "MOVE 'AB' TO TB OF HT(2).",
        "MOVE 'ZZ' TO TB OF HT(3).",
    ]
    assert _evaluate("TB OF HT(I)", *fill) == 1


@covers(CobolFeature.EVALUATE)
def test_a_plain_subject_still_matches():
    assert _evaluate("WS-A") == 1


@covers(CobolFeature.EVALUATE)
def test_when_thru_and_when_other_are_unaffected():
    region = first_region(
        run_cobol(
            _program(
                "MOVE 5 TO D",
                "EVALUATE D",
                "   WHEN 1 THRU 4 MOVE 1 TO D",
                "   WHEN 5 THRU 9 MOVE 2 TO D",
                "   WHEN OTHER MOVE 9 TO D",
                "END-EVALUATE.",
            )
        )
    )
    assert decode_zoned_unsigned(region, _D, 4) == 2
