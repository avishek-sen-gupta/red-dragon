"""Every form the COBOL subscript grammar accepts, exercised from source.

``Cobol.g4``'s ``subscript`` rule offers five alternatives (``ALL |
integerLiteral | qualifiedDataName | indexName | arithmeticExpression``) and
``tableCall`` makes the separating comma optional, so the same reference can be
spelled many ways. This file pins the runtime meaning of each spelling.

It exists because the grammar silently merged adjacent subscripts
(red-dragon-5wp3): ``qualifiedDataName integerLiteral?`` swallowed the integer
following a data name, so ``TBL(WS-I, 3)`` parsed as ONE subscript and
``createValueStmt`` then kept the literal and discarded ``WS-I`` — a 2-D
reference collapsing to 1-D and reading the wrong element with no error at all.
A silent wrong answer is only catchable from source, which is why these are
execution tests and not bridge-JSON assertions.

Each table cell holds ``row * 10 + col`` so an assertion names the cell it
expects; ``OUTF`` is the first 01 in WORKING-STORAGE, hence at region offset 0.
"""

from __future__ import annotations

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
)
from tests.integration.cobol_helpers import decode_zoned_unsigned as _decode
from tests.integration.cobol_helpers import first_region as _first_region

_OUTF_LEN = 4


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):  # noqa: F811
    """Enforce the required PROLEAP_BRIDGE_JAR (fails loudly if unset)."""


def _outf(lines: list[str]) -> int:
    """Run the program and read OUTF, the first 01 in WORKING-STORAGE."""
    return _decode(_first_region(run_cobol(lines)), 0, _OUTF_LEN)


# ── 2-D table: the shape the merge bug corrupts ──────────────────────────────
_TWO_DIM_DATA = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SUBGRAM.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 OUTF                      PIC 9(4) VALUE 0.",
    "01 WS-TAB.",
    "   05 WS-ROW OCCURS 3 TIMES.",
    "      10 WS-CELL OCCURS 3 TIMES PIC 9(4).",
    "01 WS-I                      PIC 9(1) VALUE 2.",
    "01 WS-J                      PIC 9(1) VALUE 3.",
    "PROCEDURE DIVISION.",
    "MAIN.",
]
_TWO_DIM_INIT = [
    f"    MOVE {r}{c} TO WS-CELL({r}, {c})" for r in (1, 2, 3) for c in (1, 2, 3)
]


def _two_dim(statement: str) -> list[str]:
    return _TWO_DIM_DATA + _TWO_DIM_INIT + [f"    {statement}", "    STOP RUN."]


# (label, subscript spelling, expected cell). WS-I is 2 and WS-J is 3
# throughout, so every spelling below names cell (2,3) unless stated.
_TWO_DIM_CASES = [
    ("both literals, comma", "MOVE WS-CELL(2, 3) TO OUTF", 23),
    ("both literals, space", "MOVE WS-CELL(2 3) TO OUTF", 23),
    ("both data names, comma", "MOVE WS-CELL(WS-I, WS-J) TO OUTF", 23),
    ("both data names, space", "MOVE WS-CELL(WS-I WS-J) TO OUTF", 23),
    ("data name then literal, comma", "MOVE WS-CELL(WS-I, 3) TO OUTF", 23),
    ("data name then literal, space", "MOVE WS-CELL(WS-I 3) TO OUTF", 23),
    ("literal then data name, comma", "MOVE WS-CELL(2, WS-J) TO OUTF", 23),
    ("literal then data name, space", "MOVE WS-CELL(2 WS-J) TO OUTF", 23),
    ("space before the paren", "MOVE WS-CELL (WS-I, WS-J) TO OUTF", 23),
    ("space before paren, mixed", "MOVE WS-CELL (WS-I, 3) TO OUTF", 23),
    ("arithmetic in second position", "MOVE WS-CELL(WS-I, WS-I + 1) TO OUTF", 23),
    ("arithmetic in first position", "MOVE WS-CELL(WS-I + 1, WS-J) TO OUTF", 33),
    ("subtraction subscript", "MOVE WS-CELL(WS-J - 1, WS-J) TO OUTF", 23),
]


@covers(CobolFeature.SUBSCRIPT_ACCESS)
@pytest.mark.parametrize(
    "statement,expected",
    [(s, e) for _, s, e in _TWO_DIM_CASES],
    ids=[label for label, _, _ in _TWO_DIM_CASES],
)
def test_two_dim_subscript_spelling_selects_the_named_cell(statement, expected):
    assert _outf(_two_dim(statement)) == expected


# ── 1-D relative subscripting: data-name +/- integer is ONE subscript ────────
_ONE_DIM_DATA = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SUBGRM1.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 OUTF                      PIC 9(4) VALUE 0.",
    "01 WS-TAB.",
    "   05 WS-ELEM OCCURS 3 TIMES PIC 9(4).",
    "01 WS-I                      PIC 9(1) VALUE 2.",
    "PROCEDURE DIVISION.",
    "MAIN.",
    "    MOVE 10 TO WS-ELEM(1)",
    "    MOVE 20 TO WS-ELEM(2)",
    "    MOVE 30 TO WS-ELEM(3)",
]

_ONE_DIM_CASES = [
    ("literal", "MOVE WS-ELEM(2) TO OUTF", 20),
    ("data name", "MOVE WS-ELEM(WS-I) TO OUTF", 20),
    ("space before paren", "MOVE WS-ELEM (WS-I) TO OUTF", 20),
    ("relative plus", "MOVE WS-ELEM(WS-I + 1) TO OUTF", 30),
    ("relative minus", "MOVE WS-ELEM(WS-I - 1) TO OUTF", 10),
    ("arithmetic literal only", "MOVE WS-ELEM(1 + 1) TO OUTF", 20),
]


@covers(CobolFeature.SUBSCRIPT_ACCESS)
@pytest.mark.parametrize(
    "statement,expected",
    [(s, e) for _, s, e in _ONE_DIM_CASES],
    ids=[label for label, _, _ in _ONE_DIM_CASES],
)
def test_one_dim_subscript_spelling_selects_the_named_element(statement, expected):
    assert _outf(_ONE_DIM_DATA + [f"    {statement}", "    STOP RUN."]) == expected


# ── index names (INDEXED BY): the same integerLiteral? suffix applies ────────
_INDEXED_DATA = (
    [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. SUBGRMIX.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 OUTF                      PIC 9(4) VALUE 0.",
        "01 WS-TAB.",
        "   05 WS-ROW OCCURS 3 TIMES INDEXED BY R-IDX.",
        "      10 WS-CELL OCCURS 3 TIMES INDEXED BY C-IDX PIC 9(4).",
        "PROCEDURE DIVISION.",
        "MAIN.",
    ]
    + _TWO_DIM_INIT
    + [
        "    SET R-IDX TO 2",
        "    SET C-IDX TO 3",
    ]
)

_INDEXED_CASES = [
    ("both index names", "MOVE WS-CELL(R-IDX, C-IDX) TO OUTF", 23),
    ("index name then literal", "MOVE WS-CELL(R-IDX, 3) TO OUTF", 23),
    ("literal then index name", "MOVE WS-CELL(2, C-IDX) TO OUTF", 23),
    ("index name, space separated", "MOVE WS-CELL(R-IDX C-IDX) TO OUTF", 23),
]


@covers(CobolFeature.SUBSCRIPT_ACCESS)
@pytest.mark.parametrize(
    "statement,expected",
    [(s, e) for _, s, e in _INDEXED_CASES],
    ids=[label for label, _, _ in _INDEXED_CASES],
)
def test_index_name_subscript_selects_the_named_cell(statement, expected):
    assert _outf(_INDEXED_DATA + [f"    {statement}", "    STOP RUN."]) == expected


# ── the receiving side takes the same spellings ─────────────────────────────
_TARGET_CASES = [
    ("literal target", "MOVE 77 TO WS-CELL(2, 3)"),
    ("data name target", "MOVE 77 TO WS-CELL(WS-I, WS-J)"),
    ("mixed target", "MOVE 77 TO WS-CELL(WS-I, 3)"),
    ("mixed target, space separated", "MOVE 77 TO WS-CELL(WS-I 3)"),
    ("relative target", "MOVE 77 TO WS-CELL(WS-I, WS-I + 1)"),
]


@covers(CobolFeature.SUBSCRIPT_ACCESS)
@pytest.mark.parametrize(
    "statement", [s for _, s in _TARGET_CASES], ids=[lbl for lbl, _ in _TARGET_CASES]
)
def test_subscripted_target_writes_the_named_cell(statement):
    """Every spelling writes cell (2,3); reading it back with a spelling known
    good must see 77."""
    assert (
        _outf(
            _two_dim(statement)[:-1]
            + ["    MOVE WS-CELL(2, 3) TO OUTF", "    STOP RUN."]
        )
        == 77
    )


# ── three dimensions ────────────────────────────────────────────────────────
_THREE_DIM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SUBGRM3.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 OUTF                      PIC 9(4) VALUE 0.",
    "01 WS-CUBE.",
    "   05 WS-PLANE OCCURS 2 TIMES.",
    "      10 WS-ROW OCCURS 2 TIMES.",
    "         15 WS-CELL OCCURS 2 TIMES PIC 9(4).",
    "01 WS-I                      PIC 9(1) VALUE 2.",
    "PROCEDURE DIVISION.",
    "MAIN.",
] + [
    f"    MOVE {p}{r}{c} TO WS-CELL({p}, {r}, {c})"
    for p in (1, 2)
    for r in (1, 2)
    for c in (1, 2)
]

_THREE_DIM_CASES = [
    ("all literals", "MOVE WS-CELL(2, 1, 2) TO OUTF", 212),
    ("data name first", "MOVE WS-CELL(WS-I, 1, 2) TO OUTF", 212),
    ("data name last", "MOVE WS-CELL(2, 1, WS-I) TO OUTF", 212),
    ("data name middle", "MOVE WS-CELL(2, WS-I, 2) TO OUTF", 222),
    ("space separated", "MOVE WS-CELL(2 1 2) TO OUTF", 212),
]


@covers(CobolFeature.SUBSCRIPT_ACCESS)
@pytest.mark.parametrize(
    "statement,expected",
    [(s, e) for _, s, e in _THREE_DIM_CASES],
    ids=[label for label, _, _ in _THREE_DIM_CASES],
)
def test_three_dim_subscript_spelling_selects_the_named_cell(statement, expected):
    assert _outf(_THREE_DIM + [f"    {statement}", "    STOP RUN."]) == expected


# ── the same subscripts in other statement contexts ─────────────────────────
# `subscript` is shared by every subscriptable reference, not just MOVE
# operands: relation conditions, arithmetic expressions and the level-88
# conditionNameSubscriptReference all route through it. EXEC CICS does NOT —
# ProLeap captures it as raw lines (`execCicsStatement : EXECCICSLINE*
# EXECCICSENDLINE`), so its operands are cicada's grammar, not this one.

_IF_CASES = [
    ("literal subscripts", "IF WS-CELL(2, 3) = 23", 1),
    ("data name subscripts", "IF WS-CELL(WS-I, WS-J) = 23", 1),
    ("data name then literal", "IF WS-CELL(WS-I, 3) = 23", 1),
    ("data name then literal, space", "IF WS-CELL(WS-I 3) = 23", 1),
    ("relative subscript", "IF WS-CELL(WS-I, WS-I + 1) = 23", 1),
    ("both sides subscripted", "IF WS-CELL(WS-I, 3) = WS-CELL(2, WS-J)", 1),
    ("negative case stays false", "IF WS-CELL(WS-I, 3) = 99", 9),
]


@covers(CobolFeature.SUBSCRIPT_ACCESS)
@pytest.mark.parametrize(
    "condition,expected",
    [(c, e) for _, c, e in _IF_CASES],
    ids=[label for label, _, _ in _IF_CASES],
)
def test_subscripted_operand_in_an_if_condition(condition, expected):
    """A relation condition resolves subscripts the same way a MOVE does."""
    assert (
        _outf(
            _two_dim("CONTINUE")[:-1]
            + [
                f"    {condition}",
                "        MOVE 1 TO OUTF",
                "    ELSE",
                "        MOVE 9 TO OUTF",
                "    END-IF",
                "    STOP RUN.",
            ]
        )
        == expected
    )


_COMPUTE_CASES = [
    ("literal subscripts", "COMPUTE OUTF = WS-CELL(2, 3)", 23),
    ("data name subscripts", "COMPUTE OUTF = WS-CELL(WS-I, WS-J)", 23),
    ("data name then literal", "COMPUTE OUTF = WS-CELL(WS-I, 3)", 23),
    ("data name then literal, space", "COMPUTE OUTF = WS-CELL(WS-I 3)", 23),
    ("relative subscript", "COMPUTE OUTF = WS-CELL(WS-I, WS-I + 1)", 23),
    ("two subscripted terms", "COMPUTE OUTF = WS-CELL(WS-I, 3) + WS-CELL(1, 1)", 34),
    ("subscripted term and literal", "COMPUTE OUTF = WS-CELL(WS-I, 3) * 2", 46),
]


@covers(CobolFeature.SUBSCRIPT_ACCESS)
@pytest.mark.parametrize(
    "statement,expected",
    [(s, e) for _, s, e in _COMPUTE_CASES],
    ids=[label for label, _, _ in _COMPUTE_CASES],
)
def test_subscripted_operand_in_a_compute(statement, expected):
    assert _outf(_two_dim(statement)) == expected


@pytest.mark.xfail(
    reason="red-dragon-0nj4: COMPUTE drops its receiving field's subscripts and "
    "writes occurrence 1. Pre-existing, unrelated to the subscript grammar.",
    strict=True,
)
@covers(CobolFeature.SUBSCRIPT_ACCESS)
def test_compute_writes_through_a_subscripted_target():
    """COMPUTE's receiving field takes subscripts too."""
    assert (
        _outf(
            _two_dim("COMPUTE WS-CELL(WS-I, 3) = 99")[:-1]
            + ["    MOVE WS-CELL(2, 3) TO OUTF", "    STOP RUN."]
        )
        == 99
    )


# ── level-88 condition names: conditionNameSubscriptReference ───────────────
_EIGHTY_EIGHT = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SUBGRM88.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 OUTF                      PIC 9(4) VALUE 0.",
    "01 WS-TAB.",
    "   05 WS-ROW OCCURS 3 TIMES.",
    "      10 WS-FLAG             PIC X(01).",
    "         88 FLAG-ON          VALUE 'Y'.",
    "01 WS-I                      PIC 9(1) VALUE 2.",
    "PROCEDURE DIVISION.",
    "MAIN.",
    "    MOVE 'N' TO WS-FLAG(1)",
    "    MOVE 'Y' TO WS-FLAG(2)",
    "    MOVE 'Y' TO WS-FLAG(3)",
]

_EIGHTY_EIGHT_TRUE = [
    ("literal subscript", "IF FLAG-ON(2)"),
    ("data name subscript", "IF FLAG-ON(WS-I)"),
    ("relative subscript", "IF FLAG-ON(WS-I + 1)"),
]

_EIGHTY_EIGHT_FALSE = [
    ("literal subscript", "IF FLAG-ON(1)"),
    ("data name subscript", "IF FLAG-ON(WS-I - 1)"),
]


def _eighty_eight(condition: str) -> list[str]:
    return _EIGHTY_EIGHT + [
        f"    {condition}",
        "        MOVE 1 TO OUTF",
        "    ELSE",
        "        MOVE 9 TO OUTF",
        "    END-IF",
        "    STOP RUN.",
    ]


@pytest.mark.xfail(
    reason="red-dragon-8u47: a subscripted level-88 always evaluates false, so it "
    "never fires for the occurrence it names. Pre-existing, unrelated to the "
    "subscript grammar.",
    strict=True,
)
@covers(CobolFeature.SUBSCRIPT_ACCESS)
@pytest.mark.parametrize(
    "condition",
    [c for _, c in _EIGHTY_EIGHT_TRUE],
    ids=[label for label, _ in _EIGHTY_EIGHT_TRUE],
)
def test_subscripted_condition_name_is_true_for_the_named_occurrence(condition):
    """A level-88 under OCCURS is referenced through
    conditionNameSubscriptReference, which shares the `subscript` rule."""
    assert _outf(_eighty_eight(condition)) == 1


@covers(CobolFeature.SUBSCRIPT_ACCESS)
@pytest.mark.parametrize(
    "condition",
    [c for _, c in _EIGHTY_EIGHT_FALSE],
    ids=[label for label, _ in _EIGHTY_EIGHT_FALSE],
)
def test_subscripted_condition_name_is_false_for_a_non_matching_occurrence(condition):
    assert _outf(_eighty_eight(condition)) == 9
