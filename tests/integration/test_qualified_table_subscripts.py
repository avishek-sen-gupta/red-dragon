"""A subscript written on a qualified table reference belongs to the reference.

``red-dragon-ds5t``. ANTLR takes the ``inTable`` alternative for ``TB OF HT(I)``,
so ``(I)`` ends up on the QUALIFIER's own ``tableCall`` and both subscript probes
-- the ASG-side ``extractSubscripts`` and the grammar-context
``serializeIdentifierSubscripts`` -- looked only at the operand's outer
``tableCall``, which has none. The operand serialised without a ``subscripts``
key and every such reference read or wrote occurrence 1 whatever the subscript
held. Silent wrong bytes.

The qualifier half of the same ``inTable`` blindness was ``red-dragon-64s4``.
"""

from __future__ import annotations

import json

from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import first_region, run_cobol, to_fixed

_PREAMBLE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. T.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 HT.",
    "   05 TB PIC X(5) OCCURS 3 TIMES.",
    "01 TBL.",
    "   05 TU PIC X(5) OCCURS 3 TIMES.",
    "01 GA.",
    "   05 FA PIC X(10) VALUE 'ABCDEFGHIJ'.",
    "01 NB.",
    "   05 NL PIC 9(4) VALUE 3.",
    "01 I PIC 9(2) VALUE 2.",
    "01 J PIC 9(2) VALUE 1.",
    "01 D PIC X(5) VALUE SPACES.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
]

_HT = 0
_D = 48
_WIDTH = 5


def _program(*statement_lines: str) -> list[str]:
    return [
        *_PREAMBLE,
        *(f"    {line}" for line in statement_lines),
        "    STOP RUN.",
    ]


def _source_operand(bridge_jar: str, statement_line: str) -> dict:
    raw = RealSubprocessRunner().run(
        ["java", "-jar", bridge_jar], to_fixed(_program(statement_line))
    )
    return json.loads(raw)["paragraphs"][0]["statements"][0]["operands"][0]


def _region(*statement_lines: str) -> bytearray:
    return first_region(run_cobol(_program(*statement_lines)))


def _text(region: bytearray, offset: int) -> str:
    return bytes(region[offset : offset + _WIDTH]).decode("cp037")


_FILL = [
    "MOVE 'AAAAA' TO TB OF HT(1).",
    "MOVE 'BBBBB' TO TB OF HT(2).",
    "MOVE 'CCCCC' TO TB OF HT(3).",
]


# -- The bridge JSON shape ---------------------------------------------------


@covers(CobolFeature.GROUP_ITEM, CobolFeature.SUBSCRIPT_ACCESS)
def test_a_qualified_table_reference_carries_its_subscript(bridge_jar):
    assert _source_operand(bridge_jar, "MOVE TB OF HT(I) TO D.") == {
        "name": "TB",
        "subscripts": [{"kind": "ref", "name": "I"}],
        "qualifiers": ["HT"],
    }


@covers(CobolFeature.GROUP_ITEM, CobolFeature.SUBSCRIPT_ACCESS)
@covers(CobolFeature.REFERENCE_MODIFICATION)
def test_a_sliced_qualified_table_reference_keeps_subscript_and_slice(bridge_jar):
    assert _source_operand(bridge_jar, "MOVE TB OF HT(I)(1:2) TO D.") == {
        "name": "TB",
        "subscripts": [{"kind": "ref", "name": "I"}],
        "ref_mod_start": {"kind": "lit", "value": "1"},
        "ref_mod_length": {"kind": "lit", "value": "2"},
        "qualifiers": ["HT"],
    }


@covers(CobolFeature.SUBSCRIPT_ACCESS)
def test_an_unqualified_table_reference_is_unchanged(bridge_jar):
    assert _source_operand(bridge_jar, "MOVE TU(I) TO D.") == {
        "name": "TU",
        "subscripts": [{"kind": "ref", "name": "I"}],
    }


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_a_qualified_slice_with_no_subscript_gains_none(bridge_jar):
    """``FA OF GA(1:2)`` writes a slice, not a subscript: the key stays absent."""
    operand = _source_operand(bridge_jar, "MOVE FA OF GA(1:2) TO D.")
    assert "subscripts" not in operand
    assert operand["qualifiers"] == ["GA"]


@covers(CobolFeature.GROUP_ITEM, CobolFeature.REFERENCE_MODIFICATION)
def test_a_qualified_bound_contributes_no_subscript_to_the_slice(bridge_jar):
    operand = _source_operand(bridge_jar, "MOVE FA OF GA(1:NL OF NB) TO D.")
    assert "subscripts" not in operand


# -- The bytes the program actually reads ------------------------------------


@covers(CobolFeature.GROUP_ITEM, CobolFeature.SUBSCRIPT_ACCESS)
def test_the_written_occurrence_is_the_one_read():
    """Occurrence 2 holds BBBBB; occurrence 1 holds AAAAA. Dropping the
    subscript wrote all three fills into occurrence 1 and read it back."""
    region = _region(*_FILL, "MOVE TB OF HT(I) TO D.")
    assert _text(region, _HT) == "AAAAA"
    assert _text(region, _HT + 5) == "BBBBB"
    assert _text(region, _HT + 10) == "CCCCC"
    assert _text(region, _D) == "BBBBB"


@covers(CobolFeature.GROUP_ITEM, CobolFeature.SUBSCRIPT_ACCESS)
@covers(CobolFeature.REFERENCE_MODIFICATION)
def test_a_slice_of_the_written_occurrence_reads_that_occurrence():
    region = _region(*_FILL, "MOVE TB OF HT(I)(1:2) TO D.")
    assert _text(region, _D) == "BB   "


@covers(CobolFeature.GROUP_ITEM, CobolFeature.SUBSCRIPT_ACCESS)
def test_a_literal_subscript_on_a_qualified_reference_reads_its_occurrence():
    region = _region(*_FILL, "MOVE TB OF HT(3) TO D.")
    assert _text(region, _D) == "CCCCC"
